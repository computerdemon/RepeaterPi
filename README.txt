Repeater Pi is a project to turn a raspberry pi into an amatuer radio repeater controller.

Background:  I was looking around at repeater controllers and working with hams in the area who maintain repeaters in the region. After looking at how these repeaters function and how outdated they seemed to be. Using serial interfaces and DTMP codes with software that works only in DOS or got lost and cannot be replaced was just something I didnt want to deal with. I decided to use my Pi, previously being used only as an asterisk server in a full blown gateway for amatuer radio. 

I know there are other projects out there, like OpenRepeater, but it isnt going anywhere and seems like a lot of fluff. 

My project is based on the Asterisk Phonepatch project(Arnau Sanchez). I have also used APRStt(Stephen Hamilton) as a base for most code. My project combines code from the above projects and adds a web interface and other functionality. I do not own most of the code in the project and give full credit to authors who worked hard and did an amazing job.

Features:

-Console Interface
-Web Interface
-DTMF Controllable
-Voice controllable via verbal commands
-Bot for announcements and other information
-DTMF Encoding/Decoding
-CTSS Encoding/Decoding
-CS Encoding/Decoding
-Auto Identify
-CTSS control for transmitter
-Multiple radio support
-Modular design using Asterisk to allow parts of the system to be anywhere there is an IP connection
-SIP client for connecting to Asterisk for patching and interconnecting sites
-APRS functionality
-Echolink functionality
-Remote station (use a Pi as a client with PTT mic to the repeater via asterisk)
