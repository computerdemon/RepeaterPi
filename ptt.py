#PTT Through GPIO on Pi
# GPIO and web control http://www.openhomeautomation.net/control-a-relay-from-anywhere-using-the-raspberry-pi/
# GPIO examples 
# http://www.susa.net/wordpress/2012/06/raspberry-pi-relay-using-gpio/

import RPi.GPIO as GPIO
#setup GPIO using Board numbering
GPIO.setmode(GPIO.BOARD)


def ptttxON():
	GPIO.output(18, False)
	
def ppttxOFF():
	GPIO.output(18, True)
	
def pttrxON():
	GPIO.output(16, False)
	
def pttrxOFF():
	GPIO.output(16, True)

def main():
	print 'Greetings, Enter an option'