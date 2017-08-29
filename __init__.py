import time
import re
from os.path import dirname, join

from adapt.intent import IntentBuilder
from mycroft.skills.core import MycroftSkill,intent_handler
from mycroft.util.log import getLogger
from mycroft.skills.context import *
from os.path import dirname, join
from requests import get, post
from fuzzywuzzy import fuzz
import json

__author__ = 'robconnolly, btotharye, dee'
LOGGER = getLogger(__name__)
DIM_KEYWORD={
    "up":100,
    "increase":80,
    "down": 20,
    "decrease":20,
    "minimum":10,
    "maximum":100,
    "warm":100,
    "cold":0
}

KEYWORD_EN={
    'light':'light',
    'brightness': 'brightness',
    'white' : 'white',
    'up' : 'up',
    'increase': 'increase',
    'decrease': 'decrease',
    'minimum': 'minimum',
    'maximum': 'maximum',
    'warm': 'warm',
    'cold': 'cold',
    'on': 'on',
    'off': 'off'
    }

class HomeAssistantClient(object):

    def __init__(self, host, password, port=8123, ssl=False):
        self.ssl=ssl
        self.port=int(port)
        if self.ssl:
#            port=443
            self.url = "https://%s:%d" % (host, self.port)
        else:
            self.url = "http://%s:%d" % (host, self.port)
        self.headers = {
            'x-ha-access': password,
            'Content-Type': 'application/json'
        }

    def find_entity(self, entity, types,filter=''):
        if self.ssl:
            req = get("%s/api/states" % self.url, headers=self.headers, verify=True)
        else:
            req = get("%s/api/states" % self.url, headers=self.headers)

        if req.status_code == 200:
            best_score = 0
            best_entity = None
            for state in req.json():
                try:
                    if state['entity_id'].split(".")[0] in types and re.search(filter,state['entity_id']):
                        LOGGER.debug("Entity Data: %s" % state)
                        score = fuzz.ratio(entity, state['attributes']['friendly_name'].lower())
                        if score > best_score:
                            best_score = score
                            best_entity = { "id": state['entity_id'],
                                            "dev_name": state['attributes']['friendly_name'],
                                            "state": state['state'] }
                except KeyError:
                    pass
            return best_entity
    #
    # checking the entity attributes to be used in the response dialog.
    #
    def find_entity_attr(self, entity):
        if self.ssl:
            req = get("%s/api/states" % self.url, headers=self.headers, verify=True)
        else:
            req = get("%s/api/states" % self.url, headers=self.headers)

        if req.status_code == 200:
            for attr in req.json():
                if attr['entity_id'] == entity:
                    try:
                        unit_measurement = attr['attributes']['unit_of_measurement']
                        sensor_name = attr['attributes']['friendly_name']
                        sensor_state = attr['state']
                        return unit_measurement, sensor_name, sensor_state
                    except:
                        unit_measurement = 'null'
                        sensor_name = attr['attributes']['friendly_name']
                        sensor_state = attr['state']
                        return unit_measurement, sensor_name, sensor_state

        return None

    def execute_service(self, domain, service, data):
        if self.ssl:
            post("%s/api/services/%s/%s" % (self.url, domain, service), headers=self.headers, data=json.dumps(data), verify=True)
        else:
            post("%s/api/services/%s/%s" % (self.url, domain, service), headers=self.headers, data=json.dumps(data))

    
# TODO - Localization
class HomeAssistantSkill(MycroftSkill):

    def __init__(self):
        super(HomeAssistantSkill, self).__init__(name="HomeAssistantSkill")
        self.ha = HomeAssistantClient(self.config.get('host'),
            self.config.get('password'), port=self.config.get('port','8123'),ssl=self.config.get('ssl', False))
        self.keyword=KEYWORD_EN

    def _call_ha_switch(self,ha_entity,action):
        ha_data = {'entity_id': ha_entity['id']}
        if action == "on":
            if ha_entity['state'] == action:
                self.speak_dialog('homeassistant.device.already',\
                        data={ "dev_name": ha_entity['dev_name'], 'action': action })
            else:
                self.speak_dialog('homeassistant.device.on', data=ha_entity)
                self.ha.execute_service("homeassistant", "turn_on", ha_data)
        elif action == "off":
            if ha_entity['state'] == action:
                self.speak_dialog('homeassistant.device.already',\
                        data={"dev_name": ha_entity['dev_name'], 'action': action })
            else:
                self.speak_dialog('homeassistant.device.off', data=ha_entity)
                self.ha.execute_service("homeassistant", "turn_off", ha_data)
                
    @intent_handler(IntentBuilder('LightIntent')
                    .require("SwitchKeyword").require('OnOffKeyword')
                    .require("LightEntityKeyword") #Need one_of with "EntityTypeKeyword")
                    .optionally("HomeLocKeyword")
                    .optionally("AllKeyword"))                        
    def handle_light_intent(self, message):
        #Need entity and action
        search_filter=''
        entity = None
        entity_keyword=None
        action=self.keyword[message.data.get('OnOffKeyword')]
        if message.data.get('LightEntityKeyword')==self.keyword['light']:
            if 'AllKeyword' in message.data:
                entity='all lights'
                search_scope=['group']
            elif 'HomeLocKeyword'in message.data:
                entity_keyword='HomeLocKeyword'
                entity=message.data.get(entity_keyword)               
                search_scope=['light','group']
        else:
            entity_keyword='LightEntityKeyword'
            entity=message.data.get(entity_keyword) 
            search_scope=['light','group']
        search_filter='light'
               
        if  entity == None:      
#TODO            self.speak_dialog('homeassistant.device.missing') 
            return
    
        ha_entity = self.ha.find_entity(entity, search_scope,search_filter)

        if ha_entity is None:
            self.speak_dialog('homeassistant.device.unknown', data={"dev_name":entity})
            return
        LOGGER.debug("Entity: %s" % ha_entity['dev_name'])
        LOGGER.debug("Action: %s" % action)
        if entity_keyword:
            self.set_context(entity_keyword,ha_entity['dev_name'])
        self._call_ha_switch(ha_entity,action)

                 
    @intent_handler(IntentBuilder('SwitchIntent')
                    .require("SwitchKeyword").require('OnOffKeyword')
                    .require("SwitchEntityKeyword") #,"EntityTypeKeyword")
                    .optionally("AllKeyword"))                        
    def handle_switch_intent(self, message):
        action=self.keyword[message.data.get('OnOffKeyword')]
        entity=message.data.get('SwitchEntityKeyword')
        search_scope=['switch']
        ha_entity = self.ha.find_entity(entity, search_scope)
        if ha_entity is None:
            self.speak_dialog('homeassistant.device.unknown', data={"dev_name":entity})
            return
        LOGGER.debug("Entity: %s" % ha_entity['dev_name'])
        LOGGER.debug("Action: %s" % action)
        self.set_context(entity_keyword,ha_entity['dev_name'])
        self._call_ha_switch(ha_entity['id'],action)
                
    @intent_handler(IntentBuilder('DimIntent')
                    .require("DimKeyword")
                    .require("DimValueKeyword")
                    .require("LightEntityKeyword")
                    .optionally("HomeLocKeyword"))
    def handle_dimlight_intent(self,message):
        value=message.data['DimValueKeyword']
        if not value is None:
            try:
                value=int(value)*10
            except ValueError:
                value=DIM_KEYWORD[self.keyword[value]]
        light_entity=message.data.get('LightEntityKeyword')
        if light_entity in [self.keyword['white'],self.keyword['brightness'],self.keyword['light']]:
            if 'HomeLocKeyword'in message.data:
                entity_keyword='HomeLocKeyword'                            
            if light_entity ==  self.keyword['white']:
                attribute="color_temp"
                value=int(round(value*3.46+154,0))
            else:
                attribute="brightness_pct"
        else:
            entity_keyword='LightEntityKeyword'
            attribute="brightness_pct" 
        search_scope=['light','group']            
        entity=message.data.get(entity_keyword)
        LOGGER.debug("Entity: %s" % entity)
        LOGGER.debug("Attribute: %s" % attribute)
        LOGGER.debug("Value: %s" % value)
        ha_entity = self.ha.find_entity(entity, ['group','light'])
        if ha_entity is None:
            self.speak_dialog('homeassistant.device.unknown', data={"dev_name": ha_entity['dev_name']})
            return        
        self.set_context(entity_keyword,ha_entity['dev_name'])
        ha_data = {'entity_id': ha_entity['id'],attribute: value}
        self.ha.execute_service("homeassistant", "turn_on", ha_data)
        self.speak_dialog('homeassistant.acknowledge')

    @intent_handler(IntentBuilder('ColorIntent')
                    .require("ColorKeyword")
                    .require("DimKeyword")
                    .require("LightEntityKeyword")
                    .optionally("HomeLocKeyword"))
    def handle_lightcolor_intent(self,message):
        value=message.data['ColorKeyword']
        if 'HomeLocKeyword'in message.data:
            entity_keyword='HomeLocKeyword'             
        else:
            entity_keyword='LightEntityKeyword'                
        search_scope=['light','group']            
        entity=message.data.get(entity_keyword)
        LOGGER.debug("Entity: %s" % entity)
        LOGGER.debug("Value: %s" % value)
        ha_entity = self.ha.find_entity(entity, ['group','light'])
        if ha_entity is None:
            self.speak_dialog('homeassistant.device.unknown', data={"dev_name": ha_entity['dev_name']})
            return        
        ha_data = {'entity_id': ha_entity['id'],'color_name': value}
        self.ha.execute_service("homeassistant", "turn_on", ha_data)
        self.speak_dialog('homeassistant.acknowledge')
        
    @intent_handler(IntentBuilder('CoverIntent')
                    .require("CoverKeyword").require("OpenCloseKeyword")
                    .one_of("HomeLocKeyword","AllKeyword")
                    .optionally('MinMaxKeyword').optionally('CoverValueKeyword'))
    @intent_handler(IntentBuilder('CoverIntentContext')
                    .require("CoverKeyword").require("OpenCloseKeyword")
                    .require("EntityContext"))     
    def handle_cover_intent(self,message):
    #open/close #cover #where #value
        action=message.data.get('OpenCloseKeyword')        
        value=message.data.get('CoverValueKeyword')
        if 'MinMaxKeyword' in message.data:
            value=0
        if action == "open": 
            ha_command="open_cover"
            if value is None:
                value=5
        elif action == "close":
            ha_command="close_cover"   
            if value is None:
                value=7
        else:
            ha_command="stop_cover"
            value=0
        #Entity
        if 'AllKeyword' in message.data:
            entity="alls"
        else:
            entity=message.data.get('EntityContext')        
        LOGGER.debug("Entity: %s" % entity)
        LOGGER.debug("Value: %s" % value)
        if entity==None:
            entity=message.data.get('HomeLocKeyword')
        ha_entity = self.ha.find_entity(entity, ['cover','group'],'cover')
        if ha_entity is None:
            self.speak_dialog('homeassistant.device.unknown', data={"dev_name": ha_entity['dev_name']})
            return
        ha_data = {'entity_id': ha_entity['id']}
        self.set_context('EntityContext',ha_entity['dev_name'])
        self.ha.execute_service("cover", ha_command, ha_data)
        self.speak_dialog('homeassistant.shade.action', data={"action":ha_command.split('_')[0],"dev_name": ha_entity['dev_name']})
        if value > 0:
            time.sleep(value)
            self.ha.execute_service("cover", "stop_cover", ha_data)
    def stop(self):
        pass

def create_skill():
    return HomeAssistantSkill()
