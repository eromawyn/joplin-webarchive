joplin-webarchive.py
=-=--=-=-=-=-=-=-=-=

I don’t use the WebClipper (should I ?), but I do like to keep a cached version of linked URLs in my notes.

So this script parses all modified notes every night (it should be run as a cron script), creates a copy 
of URLs inside Joplin (in the form of a new note), and modifies notes by adding a link to Joplin cached version.

Behaviour is configurable per URLs, according to regex. See config.yaml for documentation on this
matter. You may save URL as text (lynx -dump), markdown page (pandoc), PNG webshots (cutycapt), or 
PDF (wkhtmltopdf). 

By default, you need to write " (cache)" or " [cache]" after an URL to force caching it. The parser will
replace this with a link to a cache archive page. This cache archive will be in a seperated folder.

You may force cache behaviour per URL with regexes, or even cache everything ! 

Also, I do know some pages get modified often. In fact, one of my goal was to keep different versions of 
often modified pages. So by default a page is saved every 90 days. Of course, no need to updates caches. 
Just set force_refresh_on_new_link_after variable to 0 so we don’t refresh pages.

### Status

This script is at the moment a « works for me » script, although . It’s highly likely someone else might find 
this script usefull, at least, I do hope so, so I started writing this poor documentation and the script contains 
some explicit help messages so someone with knowledge in weird open sources projects might be able to run it too.

You may use it at our own risk. But I would suggest you keep a backup somewhere.

I started writing this in Python after I discovered the Joplin Perl API module wasn’t maintained anylonger.
Except I didn’t notice python module was also unmaintened... and not up to date.

As I don’t consider myself a Python coder, I wont’t update this Python joplin-api module. Instead I just 
put an ugly modified copy of this module. If Python joplin-api gets updated, I may use it instead and clean up 
my mess. In fact, I even hope I can do that one day. Any good will ?

Also, I’m pretty sure any experienced coder will complain my code is ugly. Did I say I don’t consider myself
as a Python coder ? It works for me, that’s all I want. ;p

Oh, and my English language is a mess too, sorry, it’s not my native language.

Also, if you remove all the Folder/Notes it created, but want to run it again, I would suggest you
change all the guid parameters and the uuid_salt as well in order not to recreate notes with same id, as it may 
result in sync conflicts. (I’m not sure Joplin was designed to handle non-random uuid, it’s a feature added later).

HTML notes unsupported, but I may add this feature in the future. Or if someone wants to play with BeautifulSoup,
a patch is very welcome....

## Configuration / Features

See config.yaml, it’s highly commented...

### Future

As long as I will use Joplin, I likely will continue using this script, thus also, update the code in case
of Joplin API change. And since I use Evernote since 2014, and didn’t find any better alternative than Joplin 
to suit my needs in may 2021, you may safely assume I will keep running this script for some years...

So if you see no updates in 2024, it is very likely Joplin had no major API update, and thus, this
script is still working.

I will likely also correct bugs I encounter, I’m sure there are plenty of them. 

I will also very likely correct any reported bugs which I might encounter on my setup too, so feel free to
report them.

I don’t consider myself as Python coder, but if you really paying support or need to add a feature you may hire me.

If you are a Python coder and want to send some patches, clean up my code, update the joplin-api, rewrite this 
tool, or write better documentation, feel free to do so !

### Installation

You need to install external software to parse URLs, as well as python 3, so on debian/ubuntu distributions 
just run :
```
sudo apt-get install coreutils imagemagick python3 python3-pip lynx pandoc wkhtmltopdf xvfb cutycapt
```
(Yes, that’s a lot of packages, and they have lot of dependencies too).

Also install latest version of [youtube-dl](http://ytdl-org.github.io/youtube-dl/download.html) :
```
sudo curl -L https://yt-dl.org/downloads/latest/youtube-dl -o /usr/local/bin/youtube-dl
sudo chmod a+rx /usr/local/bin/youtube-dl
```
(You are big enough to decide if you trust this unsigned "package").

It should of course work on other Linux distro, even on other Unix systems, it’s just untested.

As pandoc, wkhtmltopdf, and youtube-dl are not available on cygwin, it’s better to use a Linux system.
So only txt format will work on Cygwin. 

I know there are ports of youtube-dl to windows, I just didn’t care about testing it. 
You did ? Feel free to send a patch of this doc  (and/or the script) :) 

Then install Python modules (nothing very fancy) :
```
python -m pip install -r requirements.txt
```

And in case you use an Debian 9 ("Stretch") Server, it does not work with Python 3.5. But works with 
Python 3.7 package you can get from : https://people.debian.org/~paravoid/python-all/

Then run :
```
python3.7 -m pip install -r requirements.txt
python3.7 python3.7 joplin-webarchive.py
```

### First run

First edit config.yaml and add your joplin token. You may also edit other parameters for first run. 

In fact, you do want to read config.yaml ! It’s the best way to see features !

Then create the internal database notes :
```
python joplin-webarchive.py --first
```

You may checked this didn’t already corrupt all you Joplin data, then you may either run it on recently updated notes :
```
python joplin-webarchive.py --days 5
```

If it’s still OK, you may run it on all notes :
```
python joplin-webarchive.py --days 7000
```
(it will take some time, don’t worry, it is perfectly normal).

The parameter "7000" are days to look-up in history. So it will run all notes updated in nearly the last 20 years. 
And since Joplin isn’t that old... it should parse all notes.

### Updates

Cron every night (or at a time you know you won’t update any notes, to avoid conflicts) :
```
python joplin-webarchive.py --days 2
```

You may also cron once per week. Just increase the look-up :
```
python joplin-webarchive.py --days 8
```

If you missed updates during a few days, it’s not the end of the world, just run it manually.


### Contacts

For patches, bug reports, flowers, beers : eromawyn@gmail.com

