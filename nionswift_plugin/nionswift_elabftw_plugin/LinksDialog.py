import asyncio
import typing

import elabapy
from nion.swift.model import PlugInManager
from nion.typeshed import API_1_0
from nion.ui import Declarative
from nion.utils import Converter, Event

from nionswift_plugin.nionswift_elabftw_plugin.AsyncRequestThread import \
    AsyncRequestThread_threading

class LinksDialogUIHandler:
    def __init__(self, api: API_1_0.API, ui_view: dict, document_controller=None, elab_manager: elabapy.Manager=None, experiment_id: int=None):
        self.__api = api
        self.ui_view = ui_view
        self.document_controller = document_controller
        self.on_closed = None
        self.on_add_links = None
        self.elab_manager = elab_manager
        self.experiment_id = experiment_id
        self.check_box_states = dict()

    def init_handler(self):
        pass

    def on_load(self, widget: Declarative.UIWidget):
        if hasattr(self, 'request_close') and callable(self.request_close):
            self.request_close()

    def close(self):
        if callable(self.on_closed):
            self.on_closed()
        else:
            ... #self.request_close()

    def on_add_links_clicked(self, widget: Declarative.UIWidget):
        if callable(self.on_add_links):
            self.on_add_links()
        else:
            for item_id_str in self.check_box_states:
                if self.check_box_states[item_id_str] == True:
                    params = {'link': int(item_id_str)}
                    self.asyncthread = AsyncRequestThread_threading.asyncrequest(self.elab_manager.post_experiment, self.experiment_id, params)
                    print(f'eLabFTW plug-in: Item {params["link"]} has been linked.')

            self.request_close()
            
    def on_check_box_changed(self, widget: Declarative.UIWidget, checked: bool): # TBD
        #print(dir(widget))
        item_id_str = widget.text[:widget.text.find(':')]
        self.check_box_states[item_id_str] = checked

class LinksDialogUI:
    def get_ui_handler(self, api_broker: PlugInManager.APIBroker=None, document_controller=None, event_loop: asyncio.AbstractEventLoop=None, elab_manager: elabapy.Manager=None, experiment_id: int=None, **kwargs):
        api = api_broker.get_api('~1.0')
        ui = api_broker.get_ui('~1.0')
        self.all_items = None

        # The dialog needs to be called on UIThread, but fetching all items should be threaded out
        def tasks_sequential_calling_uithread():
            self.__fetch_all_items(elab_manager)
            def task_create_gui():
                ui_view = self.__create_ui_view(ui, title=kwargs.get('title'))
                return LinksDialogUIHandler(api, ui_view, document_controller=document_controller, elab_manager=elab_manager, experiment_id=experiment_id)
            # task_create_gui can be called outside of UI thread
            task_create_gui() # api.queue_task(task_create_gui)
        self.asyncthread = AsyncRequestThread_threading.asyncrequest(tasks_sequential_calling_uithread)

    def __create_ui_view(self, ui: Declarative.DeclarativeUI, title: str=None, **kwargs) -> dict:
        # Dynamically create check boxes
        check_boxes = []
        for item in self.all_items:
            check_boxes.append(ui.create_check_box(text=item['id']+': '+item['title'], on_checked_changed='on_check_box_changed'))
        
        # Dynamically create check box containers
        N_items = len(self.all_items)
        N_columns = 4
        items_per_column = N_items//N_columns
        check_box_columns = []
        for i in range(N_columns):
            if i < N_columns - 1:
                check_boxes_i = check_boxes[i*items_per_column:(i+1)*items_per_column]
            else:
                check_boxes_i = check_boxes[i*items_per_column:]
            check_box_columns.append(ui.create_column(*check_boxes_i, ui.create_stretch()))
        
        check_box_row = ui.create_row(*check_box_columns, ui.create_stretch()) 
            
        # Scroll area for check box columns
        check_box_scroll_area = ui.create_scroll_area(check_box_row, name='check_box_scroll_area', width='900', height='500')

        add_links_button = ui.create_push_button(text='Link selected items', on_clicked='on_add_links_clicked')
        buttons_row = ui.create_row(add_links_button, spacing=8, margin=4)

        content = ui.create_column(check_box_scroll_area, buttons_row, spacing=8, margin=4)
        return ui.create_modeless_dialog(content, title=title, margin=4)

    def __fetch_all_items(self, elab_manager: elabapy.Manager):
        self.all_items = elab_manager.get_all_items() # API yields 16 items
        print(f'{len(self.all_items)} items fetched from eLabFTW API.') # temporary feedback line

        ## TEMP workaround for the line above
        #self.all_items = []
        #for item_id in range(50):
        #    try: output = elab_manager.get_item(item_id)
        #    except: pass
        #
        #    print(item_id) # tmp
        #    if type(output) == dict:
        #        self.all_items.append(output)
        ## TEMP end


        
        
        
        