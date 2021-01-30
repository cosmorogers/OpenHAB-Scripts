# Blue Maestro Tempo Disk Scanner for MQTT
# Takes all values from the scanned tempo disc and using the MAC id pushes each topic into MQTT
# requires paho.mqtt client and bluez.
# Also requires bluemaestroscan.py in th esame directory as this has the specifics for decoding
#  the advertising packets for the Blue Maestro Tempo Disc https://www.bluemaestro.com/product/tempo-disc-temperature/
# Unsure if there are any other Blue Maetro products that it would work with.
# David@andc.nz 15/12/2016

# Credit jcs 6/8/2014 as basis

# Modified 2019-06 by JWJ:
#	- no longer uses Homie
#	- uses "simple" MQTT with topics defined in config file
#	- MQTT server info is defined in config file

import bluemaestroscan  #specific bluemaestro tempo disc scanner
import json
import sys
import argparse
import time
import logging
import bluetooth._bluetooth as bluez
import logging
import paho.mqtt.client as mqtt # pip install paho-mqtt
import paho.mqtt.publish as publish
import ssl

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dev_id = 0
FREQUENCY_SECONDS = 600
LOG = "/var/log/mqtt.home.bluetooth.log"

# Define event callbacks
def on_connect(client, userdata, flags, rc):
    print("rc: " + str(rc))

def on_message(client, obj, msg):
    print(msg.topic + " " + str(msg.qos) + " " + str(msg.payload))

def on_publish(client, obj, mid):
    print("mid: " + str(mid))

def on_subscribe(client, obj, mid, granted_qos):
    print("Subscribed: " + str(mid) + " " + str(granted_qos))

def on_log(client, obj, level, string):
    print(string)

# Initialize MQTT client and assign callbacks (global scope so we can disconnect from outer exception handler)
mqttc = mqtt.Client()	# Default parameters. Auto-generate client name
mqttc.on_message = on_message
mqttc.on_connect = on_connect
mqttc.on_publish = on_publish
mqttc.on_subscribe = on_subscribe

friendlyNames = {
	"FD31DA50": "side_shed",
	"DED3F59D": "shed",
	"DF9928DF": "garden",
    "E3020F4B": "network_cabinet"
}


def main( configfile='homie-bluetooth.json' ):
	# Read config
	print "Loading config from: " + configfile
	with open( configfile ) as json_file:  
		config = json.load( json_file )

	print "Configuration:"
	print config

	MOSQUITTO_HOST = config["MQTT"]["HOST"]
	MOSQUITTO_PORT = config["MQTT"]["PORT"]
	MOSQUITTO_KEEPALIVE = config["MQTT"]["KEEPALIVE"]
	MOSQUITTO_USER = config["MQTT"]["USERNAME"]
	MOSQUITTO_PWD = config["MQTT"]["PASSWORD"]

	# Set freq and log filename
	FREQUENCY_SECONDS =config["bluetooth"]["frequency"]
	LOG = config["bluetooth"]["log"]
	logging.basicConfig(filename=LOG, level=logging.ERROR,format='%(asctime)s %(levelname)s %(message)s')   
	
	# Set MQTT credentials, open connection and start background network loop
	print "Connecting to {0}:{1}".format( MOSQUITTO_HOST, MOSQUITTO_PORT )
	# mqttc.username_pw_set( MOSQUITTO_USER, MOSQUITTO_PWD )
	# mqttc.tls_set( ca_certs=config["MQTT"]["TLS_CERT"] )
	mqttc.connect( MOSQUITTO_HOST, MOSQUITTO_PORT, MOSQUITTO_KEEPALIVE )
	mqttc.loop_start()

	try:
		sock = bluez.hci_open_dev(dev_id)

	except:
		print "error accessing bluetooth device..."
		logging.error("error accessing bluetooth device...")
	    	sys.exit(1)
	
	bluemaestroscan.hci_le_set_scan_parameters(sock)
	bluemaestroscan.hci_enable_le_scan(sock)

	while True:
		try:
			returnedList = bluemaestroscan.parse_events( sock )
			currentdatetime = time.strftime( "%Y-%m-%dT%H:%M:%S" )	# 2019-06-25T23:59:00
			print('Date Time:   {0}'.format( currentdatetime ))
			print "number of beacons found {0}".format(len(returnedList))

			for beacon in returnedList:
				# Publish to the MQTT channel
				try:
					mac = beacon["name"]
					name = friendlyNames[beacon["name"]]
					temp = float( beacon["temp"] )
					humidity = float( beacon["humidity"] )
					dewpoint = beacon["dewpoint"]
					battery = "{:.2f}".format(beacon["battery"])

					print "Mac: {0}, Name: {1}, Temp: {2} C, humidity: {3}%, dewpoint: {4} C, battery: {5}%".format( mac, name, temp, humidity, dewpoint, battery )

					mqttc.publish( "/bluemaestro/{0}".format(name), json.dumps({
						"name": name,
						"temp": temp,
						"humidity": humidity,
						"dewpoint": dewpoint,
						"battery": battery,
						"timestamp": currentdatetime
					}) )

				except Exception,e:
					# Null out the worksheet so a login is performed at the top of the loop.
					logging.error('Append error, logging in again: ' + str(e))
					logging.error("Sleeping for 60 seconds")
					time.sleep(60)
					continue

			# If we didn't find any matching BLE devices, wait 1 sec.; otherwise wait the speficied amount
			if len( returnedList ) > 0:
				time.sleep( FREQUENCY_SECONDS )
			else:
				time.sleep( 1 )

		except Exception as e:
	       	# Error appending data, most likely because credentials are stale.
			# Null out the worksheet so a login is performed at the top of the loop.
			print('Append error, logging in again: ' + str(e))
			print "Sleeping for 60 seconds"
			time.sleep(60)
			continue

if __name__ == '__main__':
    try:
        parser= argparse.ArgumentParser( description="MQTT Based Bluetooth Reader" )
        parser.add_argument( '-c','--configfile', help='Configuration filename (json)',required=True )
        args = parser.parse_args()
        main(args.configfile)
    except (KeyboardInterrupt, SystemExit):
		mqttc.loop_stop()
		mqttc.disconnect()
		print "Top-level exception - terminating."
