#
# Copyright (c) 2014 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public License,
# version 2 (GPLv2). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
# along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#
# Red Hat trademarks are not licensed under GPLv2. No permission is
# granted to use or replicate Red Hat trademarks that are incorporated
# in this software or its documentation.
#
import gettext
import logging

# rhsm.conf->iniparse->configParser can raise ConfigParser exceptions
import ConfigParser

from subscription_manager import certlib
from subscription_manager import models

from subscription_manager.plugin.ostree import model

# plugins get
log = logging.getLogger('rhsm-app.' + __name__)

_ = gettext.gettext


OSTREE_CONTENT_TYPE = "ostree"


class OstreeContentUpdateActionCommand(object):
    """UpdateActionCommand for ostree repos.

    Update the repo configuration for rpm-ostree when triggered.

    Return a OstreeContentUpdateReport.
    """
    def __init__(self, ent_source=None):
        self.ent_source = ent_source or []

    def perform(self):

        # starting state of ostree config
        ostree_config = model.OstreeConfig()

        # populate config, handle exceptions
        self.load_config(ostree_config)

        report = OstreeContentUpdateActionReport()

        # return the composed set oEntitledContents
        entitled_contents = OstreeContents(ent_source=self.ent_source)

        # CALCULATE UPDATES
        # given current config, and the new contents, construct a list
        # of remotes to apply to our local config of remotes.
        updates_builder = \
            model.OstreeConfigUpdatesBuilder(ostree_config,
                                             contents=entitled_contents)
        updates = updates_builder.build()

        log.debug("Updates orig: %s" % updates.orig)
        log.debug("Updates new: %s" % updates.new)
        log.debug("Updates.new.remote_set: %s" % updates.new.remotes)

        # persist the new stuff
        updates.apply()
        updates.save()

        report.orig_remotes = list(updates.orig.remotes)
        report.remote_updates = list(updates.new.remotes)

        # Now that we've updated the ostree repo config, we need to
        # update the currently deployed osname tree .origin file:
        self.update_origin_file(ostree_config)

        log.debug("Ostree update report: %s" % report)
        return report

    def load_config(self, ostree_config):
        try:
            ostree_config.load()
        except ConfigParser.Error:
            log.info("No ostree content repo config file found. Not loading ostree config.")

    def update_origin_file(self, ostree_config):
        updater = model.OstreeOriginUpdater(ostree_config)
        updater.run()


class OstreeContents(object):
    """Find the ostree content provided by our current entitlements.

    Find the ostree content, meaning having a content type of
    'ostree', but also meeting any other requirements ostree has
    of it's content types (like, having a url and a name).

    Potentially filtering on product tags.

    Note: this is building the list of Contents, not neccasarily
    the list of ostree remotes or repos.

    This could disambiquate content dupes as well.
    """
    content_type = OSTREE_CONTENT_TYPE

    def __init__(self, ent_source=None):
        self._contents = models.EntCertEntitledContentSet()
        self.ent_source = ent_source or []

        self._load()

    def _load(self):
        """Populate self._contents with data from ostree contents."""
        for entitlement in self.ent_source:
            for content in entitlement.contents:
                log.debug("content: %s" % content)

                if self.content_type_match(content):
                    log.debug("adding %s to ostree content" % content)
                    # no uniq constraint atm
                    self._contents.add(content)

    def content_type_match(self, content):
        return content.content_type == self.content_type

    # We could subclass models.Contents. We would be
    # a models.Contents and have-a models.EntCertEntitledContentSet
    def __iter__(self):
        return iter(self._contents)

    def __len__(self):
        return len(self._contents)

    def __getitem__(self, key):
        return self._contents[key]


class OstreeContentUpdateActionReport(certlib.ActionReport):
    """Track ostree repo config changes."""
    name = "Ostree repo updates report"

    def __init__(self):
        super(OstreeContentUpdateActionReport, self).__init__()
        self.orig_remotes = []
        self.remote_updates = []
        self.remote_added = []
        self.remote_deleted = []
        self.content_to_remote = {}

    def updates(self):
        """Number of updates. Approximately."""
        return len(self.remote_updates)

    def _format_remotes(self, remotes):
        s = []
        for remote in remotes:
            s.append(remote.report())
        return '\n'.join(s)

    def __str__(self):
        s = ["Ostree repo updates\n"]
        s.append(_("Updates:"))
        s.append(self._format_remotes(self.remote_updates))
        s.append(_("Added:"))
        s.append(self._format_remotes(self.remote_updates))
        s.append(_("Deleted:"))
        s.append(self._format_remotes(self.orig_remotes))
        return '\n'.join(s)
