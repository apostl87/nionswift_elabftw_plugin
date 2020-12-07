import asyncio
import gettext
import io
import json
import multiprocessing
import os
import sys
import typing
import time
from datetime import datetime
from urllib.parse import urlparse

import elabapy
from nion.swift import DocumentController, Facade, Panel, Workspace
from nion.swift.model import PlugInManager
from nion.typeshed import API_1_0
from nion.ui import Declarative
from nion.utils import Event, Registry

from nionswift_plugin.nionswift_elabftw_plugin.AsyncRequestThread import \
    AsyncRequestThread_QT, AsyncRequestThread_threading
#from nionswift_plugin.nionswift_elabftw_plugin.AsyncRequestWrapper import \
#    AsyncRequestWrapper

from nionswift_plugin.nionswift_elabftw_plugin.MergeDataConfirmDialog import \
    MergeDataConfirmDialogUI
from nionswift_plugin.nionswift_elabftw_plugin.LinksDialog import \
    LinksDialogUI

from nionswift_plugin.nionswift_elabftw_plugin.Users import Users

import nionswift_plugin.nionswift_elabftw_plugin.Tools as tools

_ = gettext.gettext

#### pnm-specific: inside/outside of the pnm network
## import socket module
import socket
## get name of host by socket.gethostname
hostname = socket.gethostname()
## get IP address using socket.gethostbyname
ip_address = socket.gethostbyname(hostname)
print(f"eLabFTW plug-in init: Your IPv4 is {ip_address}.")
if '131.130' in ip_address:
    pass
else:
    os.environ['HTTPS_PROXY'] = 'socks5://127.0.0.1:1234' # run your "pnmgate.sh -w" beforehand
#### end

class ElabFTWUIHandler:
    def __init__(self, api: API_1_0.API, event_loop: asyncio.AbstractEventLoop, ui_view: dict):
        self.ui_view = ui_view
        self.__api = api
        self.__event_loop = event_loop
        self.property_changed_event = Event.Event()
        self.undo_metadata = None
        self.last_modified_dataitem = None
        self.combo = None
        # master or pnm-specific: use threading instead of qt
        self.asyncthread_package = 'threading' # options: 'qt', 'threading'
        # pnm functionality: properties for readable GUI elements
        self.__add_tag_text = None
        self.__add_link_text = None
        self.__append_line2body_text = None
        self.__create_experiment_text = None
        self.__current_experiment_id = None
        self.__current_experiment_title = None
        self.set_status = None

    def init_handler(self):
        # Needed for method "spawn" (on Windows) to prevent mutliple Swift instances from being started
        if multiprocessing.get_start_method() == 'spawn':
            multiprocessing.set_executable(os.path.join(sys.exec_prefix, 'pythonw.exe'))
        self.users = Users()
        self.combo.items = self.users.get_users_list()
        self.users.username = self.combo.items[0]
        self.elab_manager = None

        #Check if directory exists or not. Create if it doesn't exist.
        from pathlib import Path
        Path(os.path.expanduser(self.users.settings_dir)).mkdir(parents=True, exist_ok=True)

    def close(self):
        ...

    def ask_save_url(self, msg='Enter elabftw URL'):
        def save_url(url):
            with open(os.path.expanduser(self.users.settings_dir)+'/config.txt', 'a+') as f:
                f.write('elabftw_url='+url+'\n')

        def url_check(url):
            #Checks and accounts for different formats the address could be given in
            url_result = urlparse(url)
            if(url_result.netloc==''): #If no valid netloc found
                #ask again
                self.ask_save_url('Incorrect URL. Please enter the URL from the address bar in your browser.')
            else:
                save_url(url_result.scheme+"://"+url_result.netloc)

        self.__api.application.document_windows[0].show_get_string_message_box('eLabFTW Server Address', msg, url_check, accepted_text='Save')

    def setup_config(self):
        # Returns true if config already exists
        # Returns false to allow caller to interrupt action
        # Get url of Elab Server
        self.config = {}
        with open(os.path.expanduser(self.users.settings_dir)+'/config.txt', 'a+') as f:
            f.seek(0)
            for prop in f:
                prop = prop.rstrip('\n').split('=')
                self.config[prop[0]] = prop[1]
                print("eLabFTW plugin config directory: "+os.path.expanduser(self.users.settings_dir))
                print(self.config)

            if len(self.config) < 1: #If no config is found
                # Ask for and save url address
                self.ask_save_url()
                return False
            return True

    def get_experiments_and_set(self):
        def task_set_experiments(experiments=None):
            self.experiments = experiments if experiments is not None else self.elab_manager.get_all_experiments()
            self.experiments.append({'id':'-1', 'title':'<Create Experiment>'})

        def task_update_ui():
            self.ui_stack.current_index = 1
            self.experiments_combo.items = [x['title'] for x in self.experiments]
            self.current_experiment_id = self.experiments[self.combo.current_index]['id']
            self.get_uploads_for_current_experiment()

        # Use QThread or threading
        # Keep the reference self.asyncthread.
        # It ensures that the garbage collector cannot intervene.
        if self.asyncthread_package == 'qt':            
            def tasks_sequential(experiments=None):
                task_set_experiments(experiments=experiments)
                task_update_ui()
            self.asyncthread = AsyncRequestThread_QT.asyncrequest(self.elab_manager.get_all_experiments, tasks_sequential)
        elif self.asyncthread_package == 'threading':
            def tasks_sequential_calling_uithread(experiments=None):
                task_set_experiments(experiments=experiments)
                self.__api.queue_task(task_update_ui)
            self.asyncthread = AsyncRequestThread_threading.asyncrequest(tasks_sequential_calling_uithread)
        else:
            print('Chosen asynchronous threading package not implemented.')

    def switch_to_experiments_list(self):
        self.elab_manager = elabapy.Manager(endpoint=self.config['elabftw_url']+"/api/v1/", token=self.users.api_key)
        ## pnm-specific: Tests the API functionality
        #exp = self.elab_manager.get_experiment(42)
        #print(json.dumps(exp, indent=4, sort_keys=True))
        ## end
        self.get_experiments_and_set()

    def logout_user_button_clicked(self, widget: Declarative.UIWidget):
        self.users.logout()
        self.combo.items = self.users.get_users_list()
        self.users.username = self.combo.items[0]
        self.ui_stack.current_index = 0

    def create_user_button_clicked(self, widget: Declarative.UIWidget):
        def reject_colon(text):
            if ':' in text:
                raise Exception('There should be no colon ":" in the entry.')

        def accepted_api_dialog(api):
            reject_colon(api)
            self.users.api_key = api
            self.users.create_user()
            self.switch_to_experiments_list()

        def accepted_elabftw_user_id_dialog(user_id):
            try: int(user_id)
            except: raise Exception('Invalid format for Person id')
            self.users.elabftw_user_id = user_id
            self.__api.application.document_windows[0].show_get_string_message_box('Create User', 'Enter API key', accepted_api_dialog, accepted_text='Set')

        def accepted_pass_dialog(password):
            reject_colon(password)
            if self.users.password == password:
                self.__api.application.document_windows[0].show_get_string_message_box('Create User', 'Enter eLabFTW item id for your Person', accepted_elabftw_user_id_dialog, accepted_text='Set')
            else:
                self.users.password = password
                self.__api.application.document_windows[0].show_get_string_message_box('Create User', 'Repeat password', accepted_pass_dialog, accepted_text='Confirm')

        def accepted_user_dialog(name):
            reject_colon(name)
            self.users.username = name
            self.__api.application.document_windows[0].show_get_string_message_box('Create User', 'Choose a local password', accepted_pass_dialog, accepted_text='Set')

        if self.setup_config():
            self.__api.application.document_windows[0].show_get_string_message_box('Create User', 'Choose a local username', accepted_user_dialog, accepted_text='Create')

    def login_user_button_clicked(self, widget: Declarative.UIWidget):
        def on_password_input(password):
            if self.users.login(self.users.username, password):
                self.__api.application.document_windows[0].show_get_string_message_box('Create Experiment',
                                        'Experiment title [Leave empty to not create a new Experiment]', self.create_experiment_, accepted_text='Continue')
                self.switch_to_experiments_list()
            else:
                self.__api.application.document_windows[0].show_get_string_message_box('Login', 'Wrong password. Please try again.', on_password_input, accepted_text='Login')

        if self.setup_config():
            self.__api.application.document_windows[0].show_get_string_message_box('Login', 'Enter password', on_password_input, accepted_text='Login')

    def upload_meta_data(self):
        for i, dataitem in enumerate(self.__api.application.document_controllers[0]._document_controller.selected_data_items):
            metadata = dataitem.metadata
            metadata['uuid'] = str(dataitem.uuid)
            f = io.StringIO(json.dumps(metadata, indent=3))
            f.name = dataitem.title+'.json'
            files = {'file': f}
            if self.asyncthread_package == 'qt':
                self.asyncthread = AsyncRequestThread_QT.asyncrequest(self.elab_manager.upload_to_experiment, None, self.current_experiment_id, files)
            elif self.asyncthread_package == 'threading':
                self.asyncthread = AsyncRequestThread_threading.asyncrequest(self.elab_manager.upload_to_experiment, self.current_experiment_id, files)
            else:
                print('Debug: Chosen asynchronous threading package not implemented.')
        
        print(f'eLabFTW plug-in: Metadata of {i+1} items has been submitted.')

        # Reset current index matching with UI
        def task_set_experiments(experiments=None):
            self.experiments = experiments if experiments is not None else self.elab_manager.get_all_experiments()
            self.experiments = self.elab_manager.get_all_experiments()
            self.experiments.append({'id':'-1', 'title':'<Create Experiment>'})
        def task_reset_ui():
            self.combo.items = [x['title'] for x in self.experiments]
            self.get_uploads_for_current_experiment()

        if self.asyncthread_package == 'qt':            
            def tasks_sequential(experiments=None):
                task_set_experiments(experiments=experiments)
                task_reset_ui()
            self.asyncthread = AsyncRequestThread_QT.asyncrequest(self.elab_manager.get_all_experiments, tasks_sequential)
        elif self.asyncthread_package == 'threading':
            def tasks_sequential_calling_uithread(experiments=None):
                task_set_experiments(experiments=experiments)
                self.__api.queue_task(task_reset_ui)
            self.asyncthread = AsyncRequestThread_threading.asyncrequest(tasks_sequential_calling_uithread)
        else:
            print('Chosen asynchronous threading package not implemented.')

    def on_combo_changed(self, widget: Declarative.UIWidget, current_index: int):
        self.users.username = self.combo.items[current_index]

    def on_uploads_combo_changed(self, widget: Declarative.UIWidget, current_index: int):
        self.current_upload_id = self.uploads[current_index]['id']

    def on_experiments_combo_changed(self, widget: Declarative.UIWidget, current_index: int):
        self.current_experiment_id = self.experiments[current_index]['id']

        if self.current_experiment_id == '-1':
            return
        # sync the uploads with the chosen experiments
        self.get_uploads_for_current_experiment()

    def get_uploads_for_current_experiment(self):
        def task_lookup_current_experiment(exp=None):
            self.exp = exp if exp is not None else self.elab_manager.get_experiment(self.current_experiment_id)
        
        def task_ui():
            if self.exp['has_attachment'] == '1':
                self.uploads = [{'real_name':x['real_name'],'id':x['id']} for x in self.exp['uploads']]
                self.uploads_combo.items = [x['real_name'] for x in self.uploads]
                self.current_upload_id = self.uploads[self.uploads_combo.current_index]['id']
            else:
                self.uploads = []
                self.uploads_combo.items = ['No attachments found!']
                self.current_upload_id = '-1'

        if self.asyncthread_package == 'qt':
            def tasks_sequential(exp=None):
                task_lookup_current_experiment(exp=exp)
                task_ui()
            self.asyncthread = AsyncRequestThread_QT.asyncrequest(self.elab_manager.get_experiment, tasks_sequential, self.current_experiment_id)
        elif self.asyncthread_package == 'threading':
            def tasks_sequential_calling_uithread(exp=None):
                task_lookup_current_experiment(exp=exp)
                self.__api.queue_task(task_ui)
            self.asyncthread = AsyncRequestThread_threading.asyncrequest(tasks_sequential_calling_uithread)
        else:
            print('Chosen asynchronous threading package not implemented.')

    def submit_data_button_clicked(self, widget: Declarative.UIWidget):
        #check if one or more dataitem is selected. Otherwise raise an error.
        if len(self.__api.application.document_controllers[0]._document_controller.selected_data_items)<1:
            self.__api.application.document_windows[0].show_get_string_message_box('Error in Dataitem selection', 'Please select data item(s) to submit in the Data Panel.', lambda x: x)
            return

        if self.current_experiment_id == str(-1):
            def accepted_exp_dialog(experiment_name):
                self.create_experiment_(experiment_name, uploadFlag=True)
            self.__api.application.document_windows[0].show_get_string_message_box('Create Experiment', 'Enter a name for the Experiment', accepted_exp_dialog, accepted_text='Create')
        else:
            self.upload_meta_data()

    def fetch_data_button_clicked(self, widget: Declarative.UIWidget):
        document_controller = self.__api.application.document_controllers[0]._document_controller

        #check if one dataitem is selected. Otherwise give an error.
        if len(document_controller.selected_data_items)!=1:
            self.__api.application.document_windows[0].show_get_string_message_box('Error in Dataitem selection', 'Please choose a single data item to fetch to.', lambda x: x)
            return

        selected_dataitem = document_controller.selected_data_items[0]
        self.last_modified_dataitem = selected_dataitem
        self.undo_metadata = selected_dataitem.metadata # save metadata to undo

        def show_metadata_diff(metadata_elab):
            metadata_elab = json.loads(metadata_elab.decode('utf-8'))
            if 'uuid' in metadata_elab:
                del metadata_elab['uuid']
            self.ui_handler = MergeDataConfirmDialogUI().get_ui_handler(api_broker=PlugInManager.APIBroker(), document_controller=document_controller, 
                                                                        event_loop=document_controller.event_loop, metadata_elab=metadata_elab,
                                                                        metadata_nion=selected_dataitem.metadata, dataitem=selected_dataitem, title='Merge metedata')
            self.finishes = list()
        def task_ui():
            dialog = Declarative.construct(document_controller.ui, document_controller, self.ui_handler.ui_view, self.ui_handler, self.finishes)
            for finish in self.finishes:
               finish()
            self.ui_handler._event_loop = document_controller.event_loop

            self.ui_handler.request_close = dialog.request_close
            dialog.show()
        
        if self.asyncthread_package == 'qt':
            def tasks_sequential(metadata_elab):
                show_metadata_diff(metadata_elab)
                task_ui()
            self.asyncthread = AsyncRequestThread_QT.asyncrequest(self.elab_manager.get_upload, tasks_sequential, self.current_upload_id)
        elif self.asyncthread_package == 'threading':
            def tasks_sequential_calling_uithread():
                show_metadata_diff(self.elab_manager.get_upload(self.current_upload_id))
                self.__api.queue_task(task_ui)
            self.asyncthread = AsyncRequestThread_threading.asyncrequest(tasks_sequential_calling_uithread)
        else:
            print('Chosen asynchronous threading package not implemented.')

    def undo_change_button_clicked(self, widget: Declarative.UIWidget):
        if self.undo_metadata != None:
            self.last_modified_dataitem.metadata = self.undo_metadata

    def add_tag_button_clicked(self, widget: Declarative.UIWidget):
        def task_add_tag():
            params = {'tag': self.add_tag_text}
            # Clear line edit
            self.add_tag_text = None
            #
            self.elab_manager.post_experiment(self.current_experiment_id, params)
            print(f'eLabFTW plug-in: Tag {params["tag"]} has been added.')
        
        self.asyncthread = AsyncRequestThread_threading.asyncrequest(task_add_tag)
            
    def add_link_button_clicked(self, widget: Declarative.UIWidget):
        def task_add_link():
            params = {'link': int(self.add_link_text)}
            # Clear line edit
            self.add_link_text = None
            #
            self.elab_manager.post_experiment(self.current_experiment_id, params)
            print(f'eLabFTW plug-in: Item {params["link"]} has been linked.')

        self.asyncthread = AsyncRequestThread_threading.asyncrequest(task_add_link)

    def add_multiple_links_button_clicked(self, widget: Declarative.UIWidget):
        document_controller = document_controller = self.__api.application.document_controllers[0]._document_controller
        self.ui_handler = LinksDialogUI().get_ui_handler(api_broker=PlugInManager.APIBroker(), document_controller=document_controller,
                                                        event_loop=document_controller.event_loop, elab_manager=self.elab_manager,
                                                        experiment_id=self.current_experiment_id, title='ELN items')
        self.finishes = list()
        
        # The dialog needs to be called on UIThread, but fetching all items could and should be threaded out
        dialog = Declarative.construct(document_controller.ui, document_controller, self.ui_handler.ui_view, self.ui_handler, self.finishes)
        
        for finish in self.finishes:
            finish()
        self.ui_handler._event_loop = document_controller.event_loop
        self.ui_handler.request_close = dialog.request_close
        
        dialog.show()

    def append_line2body_button_clicked(self, widget: Declarative.UIWidget):
        def task_update_experiment_body():
            tmp = self.append_line2body_text
            tmp = tools.edit_body_line(tmp, self.elab_manager)
            # Clear text edit
            self.append_line2body_text = ""
            #
            exp = self.elab_manager.get_experiment(self.current_experiment_id)
            exp['body'] += f"<p><b>[{datetime.now().strftime('%H:%M:%S')}]</b>  "
            exp['body'] += tmp
            exp['body'] += f"</p>"
            self.elab_manager.post_experiment(self.current_experiment_id, exp)
            print(f'eLabFTW plug-in: Text has been appended to Experiment body.')

        self.asyncthread = AsyncRequestThread_threading.asyncrequest(task_update_experiment_body)

    def on_set_status_combo_changed(self, widget: Declarative.UIWidget, current_index: int):
        if current_index >= 1 and current_index <= 4:
            self.set_status = current_index
        else:
            self.set_status = None

    def set_status_button_clicked(self, widget: Declarative.UIWidget):
        if self.set_status is not None:
            def task_update_experiment_status():
                params = {"category": self.set_status}
                self.elab_manager.post_experiment(self.current_experiment_id, params)
                print(f'eLabFTW plug-in: Status has been set.')
            self.asyncthread = AsyncRequestThread_threading.asyncrequest(task_update_experiment_status)
        else:
            pass

    def create_experiment_button_clicked(self, widget: Declarative.UIWidget):
        if self.create_experiment_text not in [None, '']:
            self.create_experiment_(self.create_experiment_text, uploadFlag=False)
        else:
            print('eLabFTW plug-in: Invalid Experiment name. Try again.')
        # Clear text edit
        self.create_experiment_text = ""
        #

    def finalize_button_clicked(self, widget: Declarative.UIWidget):
        pass

    def project_path_lines(self):
        out_str = "<p>"
        out_str += "<b>Path to Nion Swift Project</b>"
        out_str += "<br>"
        try: out_str += self.__api.application.document_controllers[0]._document_controller.project.storage_system_path.parent.as_uri()
        except: out_str += "Your version of Nion Swift is not compatible with this plug-in feature."
        out_str += "</p>"
        out_str += "<hr>"
        return out_str

    def create_experiment_(self, experiment_name, uploadFlag: bool=False):
        if experiment_name in ["", " "] or "not create a new Experiment" in experiment_name:
            return # this might need to be adapted und include some user feedback

        params = {'title': experiment_name,
                  'body': self.project_path_lines(),
                  'date': datetime.today().strftime('%Y%m%d'),
                }

        if self.asyncthread_package == 'qt':
            exp = self.elab_manager.create_experiment()
            print(f'eLabFTW plug-in: Experiment "{experiment_name}" created.')
            self.current_experiment_id = exp['id'] # set the id of the new experiment to upload to
            
            self.asyncthread = AsyncRequestThread_QT.asyncrequest(self.elab_manager.post_experiment, None, self.current_experiment_id, params)
            if True: # pnm-specific: add links to (1) Person entry of current user and (2) Nion UltraSTEM 100
                self.asyncthread = AsyncRequestThread_QT.asyncrequest(self.elab_manager.post_experiment, None, self.current_experiment_id, {'link': 17})
                print(f'eLabFTW plug-in: Device "Nion UltraSTEM 100" has been linked.')
                self.asyncthread = AsyncRequestThread_QT.asyncrequest(self.elab_manager.post_experiment, None, self.current_experiment_id, {'link': self.users.elabftw_user_id})
                print(f'eLabFTW plug-in: Your Person entry has been linked.')
            if uploadFlag:
                self.upload_meta_data()
            self.get_experiments_and_set()
        elif self.asyncthread_package == 'threading':
            def task_create_experiment_():
                exp = self.elab_manager.create_experiment()
                print(f'eLabFTW plug-in: Experiment "{experiment_name}" created.')
                self.current_experiment_id = exp['id'] # set the id of the new experiment to upload to
                
                self.elab_manager.post_experiment(self.current_experiment_id, params)
                if True: # pnm-specific: add link Nion UltraSTEM 100
                    self.elab_manager.post_experiment(self.current_experiment_id, {'link': 17})
                    print(f'eLabFTW plug-in: Device "Nion UltraSTEM 100" has been linked.')
                    self.elab_manager.post_experiment(self.current_experiment_id, {'link': self.users.elabftw_user_id})
                    print(f'eLabFTW plug-in: Your Person entry has been linked.')
                if uploadFlag:
                    self.upload_meta_data
                self.get_experiments_and_set()

            self.asyncthread = AsyncRequestThread_threading.asyncrequest(task_create_experiment_)
        else:
            print('Chosen asynchronous threading package not implemented.')

    @property
    def add_tag_text(self):
        return self.__add_tag_text
    
    @add_tag_text.setter
    def add_tag_text(self, value):
        self.__add_tag_text = value
        self.property_changed_event.fire("add_tag_text")
        
    @property
    def add_link_text(self):
        return self.__add_link_text
    
    @add_link_text.setter
    def add_link_text(self, value):
        try:
            value = int(value)
            self.__add_link_text = value
        except Exception:
            self.__add_link_text = None
        self.property_changed_event.fire("add_link_text")
    
    @property
    def append_line2body_text(self):
        return self.__append_line2body_text
    
    @append_line2body_text.setter
    def append_line2body_text(self, value):
        self.__append_line2body_text = value
        self.property_changed_event.fire("append_line2body_text")

    @property
    def create_experiment_text(self):
        return self.__create_experiment_text

    @create_experiment_text.setter
    def create_experiment_text(self, value):
        self.__create_experiment_text = value
        self.property_changed_event.fire("create_experiment_text")
    
    @property
    def current_experiment_id(self):
        return self.__current_experiment_id
    
    @current_experiment_id.setter
    def current_experiment_id(self, value):
        self.__current_experiment_id = value
        self.property_changed_event.fire("current_experiment_id")
        self.current_experiment_title = self.elab_manager.get_experiment(value)['title']
    
    @property
    def current_experiment_title(self):
        return self.__current_experiment_title
    
    @current_experiment_title.setter
    def current_experiment_title(self, value):
        self.__current_experiment_title = value
        self.property_changed_event.fire("current_experiment_title")

 
class ElabFTWUI:
    def __init__(self):
        self.panel_type = 'elabftw-panel'

    def get_ui_handler(self, api_broker: PlugInManager.APIBroker=None, event_loop: asyncio.AbstractEventLoop=None, **kwargs):
        api = api_broker.get_api('~1.0')
        ui = api_broker.get_ui('~1.0')
        ui_view = self.__create_ui_view(ui)
        return ElabFTWUIHandler(api, event_loop, ui_view)

    def __create_ui_view(self, ui: Declarative.DeclarativeUI) -> dict:
        # login UI
        create_user_button = ui.create_push_button(name='left_button', text='Create', on_clicked='create_user_button_clicked')
        login_user_button = ui.create_push_button(name='right_button', text='Login', on_clicked='login_user_button_clicked')
        buttons_row = ui.create_row(create_user_button, login_user_button, spacing=8, margin=4)
        
        users_combo = ui.create_combo_box(name='combo', on_current_index_changed='on_combo_changed')
        users_field = ui.create_label(name='combo_label', text='Choose user:')
        users_row = ui.create_row(users_field, users_combo)
        
        login_column = ui.create_column(users_row, buttons_row, ui.create_stretch(), spacing=8, margin=4)
        
        # experiments rows
        experiments_combo = ui.create_combo_box(name='experiments_combo', on_current_index_changed='on_experiments_combo_changed')
        experiments_field_1 = ui.create_label(text='Experiment: ')
        experiments_row_1 = ui.create_row(experiments_field_1, experiments_combo)
        experiments_field_selected = ui.create_label(text='@binding(current_experiment_title)')
        experiments_field_2 = ui.create_label(text='Selected Experiment: ')
        experiments_row_2 = ui.create_row(experiments_field_2, experiments_field_selected)

        create_experiment_line_edit = ui.create_line_edit(name='create_experiment_line_edit', text='@binding(create_experiment_text)',
                                                 placeholder_text=' Name of new Experiment ')
        create_experiment_button = ui.create_push_button(name='create_experiment_button', text='Create experiment', on_clicked='create_experiment_button_clicked')
        create_experiment_row = ui.create_row(create_experiment_line_edit, create_experiment_button)

        experiments_column = ui.create_column(experiments_row_1, experiments_row_2, create_experiment_row, spacing=8, margin=4)
        
        # manage metadata UI
        uploads_field = ui.create_label(text='Attached files: (This is a display of the list only) ')
        uploads_combo = ui.create_combo_box(name='uploads_combo', on_current_index_changed='on_uploads_combo_changed')
        uploads_row = ui.create_row(uploads_field, uploads_combo, spacing=8, margin=4)
        
        fetch_data_button = ui.create_push_button(name='fetch_button', text='Fetch metadata', on_clicked='fetch_data_button_clicked')
        undo_change_button = ui.create_push_button(name='undo_change_button', text='Undo change', on_clicked='undo_change_button_clicked')
        data_buttons_row_1 = ui.create_row() # disabled ## ui.create_row(fetch_data_button, undo_change_button)

        submit_data_button = ui.create_push_button(name='submit_button', text='Submit metadata of selected data item(s)', on_clicked='submit_data_button_clicked')
        data_buttons_row_2 = ui.create_row(submit_data_button)
        
        data_buttons_column = ui.create_column(data_buttons_row_1, data_buttons_row_2, spacing=8, margin=4)
        
        # logout UI
        logout_user_button = ui.create_push_button(name='logout_button', text='Logout', on_clicked='logout_user_button_clicked')
        logout_user_row = ui.create_row(logout_user_button, ui.create_stretch(), spacing=8, margin=4)
        
        # pnm functionality
        add_tag_line_edit = ui.create_line_edit(name='add_tag_line_edit', text='@binding(add_tag_text)', placeholder_text=' Tag ')
        add_tag_button = ui.create_push_button(name='add_tag_button', text='Add Tag', on_clicked='add_tag_button_clicked')
        add_tag_row = ui.create_row(add_tag_line_edit, add_tag_button)
        
        add_link_line_edit = ui.create_line_edit(name='add_link_line_edit', text='@binding(add_link_text)', placeholder_text=' ELN item id ')
        add_link_button = ui.create_push_button(name='add_link_button', text='Add to linked items', on_clicked='add_link_button_clicked')
        add_link_row = ui.create_row(add_link_line_edit, add_link_button)
        add_multiple_links_button = ui.create_push_button(name='add_multiple_links_button', text='Dialog: Add multiple links', on_clicked='add_multiple_links_button_clicked')
        add_links_column = ui.create_column(add_link_row, add_multiple_links_button, ui.create_stretch())

        append_line2body_text_edit = ui.create_text_edit(name='append_line2body_text_edit', text='@binding(append_line2body_text)',
                                                         placeholder_text='...', clear_button_enabled=True) #, on_text_edited='append_line2body_text_edit_edited')
        append_line2body_button = ui.create_push_button(name='append_line2body_button', text='Append text', on_clicked='append_line2body_button_clicked', )
        append_line2body_column = ui.create_column(append_line2body_text_edit, append_line2body_button)

        status_list = ['(Choose)', 'Running', 'Success', 'Need to be redone', 'Fail']
        set_status_combo = ui.create_combo_box(name='status_combo', items=status_list, on_current_index_changed='on_set_status_combo_changed')
        set_status_button = ui.create_push_button(name='set_status_button', text='Set status',  on_clicked='set_status_button_clicked')
        set_status_row = ui.create_row(set_status_combo, set_status_button)

        finalize_button = ui.create_push_button(name='finalize_button', text='Finalize (n.a. via eLabFTW API)',  on_clicked='finalize_button_clicked')
        finalize_row = ui.create_row(finalize_button)

        pnm_column = ui.create_column(add_tag_row, add_links_column, append_line2body_column, set_status_row, finalize_row, spacing=8, margin=4)

        # create final appearance of GUI
        data_column  = ui.create_column(experiments_column, uploads_row, data_buttons_column,
                                        pnm_column, logout_user_row, ui.create_stretch(),
                                        spacing=8, margin=4)
        content = ui.create_stack(login_column, data_column, name="ui_stack")
        return content


class ElabFTWPanel(Panel.Panel):
    def __init__(self, document_controller: DocumentController.DocumentController, panel_id: str, properties: dict):
        super().__init__(document_controller, panel_id, 'elabftw-panel')
        panel_type = properties.get('panel_type')
        for component in Registry.get_components_by_type('elabftw-panel'):
            if component.panel_type == panel_type:
                ui_handler = component.get_ui_handler(api_broker=PlugInManager.APIBroker(), event_loop=document_controller.event_loop)
                self.widget = Declarative.DeclarativeWidget(document_controller.ui, document_controller.event_loop, ui_handler)


def run():
    Registry.register_component(ElabFTWUI(), {'elabftw-panel'})
    panel_properties = {'panel_type': 'elabftw-panel'}
    Workspace.WorkspaceManager().register_panel(ElabFTWPanel, 'elabftw-control-panel', _('eLabFTW'), ['left', 'right'], 'left', panel_properties)
