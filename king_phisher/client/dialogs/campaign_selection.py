#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  king_phisher/client/dialogs/campaign_selection.py
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are
#  met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following disclaimer
#    in the documentation and/or other materials provided with the
#    distribution.
#  * Neither the name of the project nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
#  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
#  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
#  A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
#  OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
#  SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
#  LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
#  DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
#  THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#  (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
#  OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

from king_phisher import utilities
from king_phisher.client.assistants import CampaignCreationAssistant
from king_phisher.client import gui_utilities

from gi.repository import Gtk

__all__ = ['CampaignSelectionDialog']

class CampaignSelectionDialog(gui_utilities.GladeGObject):
	"""
	Display a dialog which allows a new campaign to be created or an
	existing campaign to be opened.
	"""
	gobject_ids = [
		'button_new_campaign',
		'button_select',
		'label_campaign_info',
		'treeview_campaigns'
	]
	top_gobject = 'dialog'
	def __init__(self, *args, **kwargs):
		super(CampaignSelectionDialog, self).__init__(*args, **kwargs)
		treeview = self.gobjects['treeview_campaigns']
		self.treeview_manager = gui_utilities.TreeViewManager(treeview, cb_delete=self._prompt_to_delete_row, cb_refresh=self.load_campaigns)
		self.treeview_manager.set_column_titles(('Campaign Name', 'Type', 'Created By', 'Creation Date', 'Expiration'), column_offset=1)
		self.popup_menu = self.treeview_manager.get_popup_menu()

		self._creation_assistant = None
		self.load_campaigns()
		# default sort is by campaign creation date, descending
		treeview.get_model().set_sort_column_id(4, Gtk.SortType.DESCENDING)

	def _highlight_campaign(self, campaign_name):
		treeview = self.gobjects['treeview_campaigns']
		store = treeview.get_model()
		store_iter = store.get_iter_first()
		while store_iter:
			if store.get_value(store_iter, 1) == campaign_name:
				treeview.set_cursor(store.get_path(store_iter), None, False)
				return True
			store_iter = store.iter_next(store_iter)
		return False

	def _prompt_to_delete_row(self, treeview, selection):
		(model, tree_iter) = selection.get_selected()
		if not tree_iter:
			return
		campaign_id = model.get_value(tree_iter, 0)
		if self.config.get('campaign_id') == campaign_id:
			gui_utilities.show_dialog_warning('Can Not Delete Campaign', self.dialog, 'Can not delete the current campaign.')
			return
		if not gui_utilities.show_dialog_yes_no('Delete This Campaign?', self.dialog, 'This action is irreversible, all campaign data will be lost.'):
			return
		self.application.rpc('db/table/delete', 'campaigns', campaign_id)
		self.load_campaigns()
		self._highlight_campaign(self.config.get('campaign_name'))

	def load_campaigns(self):
		"""Load campaigns from the remote server and populate the :py:class:`Gtk.TreeView`."""
		treeview = self.gobjects['treeview_campaigns']
		store = treeview.get_model()
		if store is None:
			store = Gtk.ListStore(str, str, str, str, str, str)
			treeview.set_model(store)
		else:
			store.clear()
		for campaign in self.application.rpc.remote_table('campaigns'):
			created_ts = utilities.datetime_utc_to_local(campaign.created)
			created_ts = utilities.format_datetime(created_ts)
			campaign_type = campaign.campaign_type
			if campaign_type:
				campaign_type = campaign_type.name
			expiration_ts = campaign.expiration
			if expiration_ts is not None:
				expiration_ts = utilities.datetime_utc_to_local(campaign.expiration)
				expiration_ts = utilities.format_datetime(expiration_ts)
			store.append([str(campaign.id), campaign.name, campaign_type, campaign.user_id, created_ts, expiration_ts])
		self.gobjects['label_campaign_info'].set_text("Showing {0:,} Campaign{1}".format(len(store), ('' if len(store) == 1 else 's')))

	def signal_assistant_destroy(self, _, campaign_creation_assistant):
		self._creation_assistant = None
		campaign_name = campaign_creation_assistant.campaign_name
		if not campaign_name:
			return
		self.load_campaigns()
		self._highlight_campaign(campaign_name)

	def signal_button_clicked(self, button):
		if self._creation_assistant is not None:
			gui_utilities.show_dialog_warning('Campaign Creation Assistant', self.dialog, 'The campaign creation assistant is already active.')
			return
		assistant = CampaignCreationAssistant(self.application)
		assistant.assistant.set_transient_for(self.dialog)
		assistant.assistant.set_modal(True)
		assistant.assistant.connect('destroy', self.signal_assistant_destroy, assistant)
		assistant.interact()
		self._creation_assistant = assistant

	def signal_treeview_row_activated(self, treeview, treeview_column, treepath):
		self.gobjects['button_select'].emit('clicked')

	def interact(self):
		self._highlight_campaign(self.config.get('campaign_name'))
		self.dialog.show_all()
		response = self.dialog.run()
		old_campaign_id = self.config.get('campaign_id')
		old_campaign_name = self.config.get('campaign_name')
		while response != Gtk.ResponseType.CANCEL:
			treeview = self.gobjects['treeview_campaigns']
			selection = treeview.get_selection()
			(model, tree_iter) = selection.get_selected()
			if tree_iter:
				break
			gui_utilities.show_dialog_error('No Campaign Selected', self.dialog, 'Either select a campaign or create a new one.')
			response = self.dialog.run()
		if response == Gtk.ResponseType.APPLY:
			campaign_id = model.get_value(tree_iter, 0)
			self.config['campaign_id'] = campaign_id
			campaign_name = model.get_value(tree_iter, 1)
			self.config['campaign_name'] = campaign_name
			if not (campaign_id == old_campaign_id and campaign_name == old_campaign_name):
				self.application.emit('campaign-set', campaign_id)
		self.dialog.destroy()
		return response
