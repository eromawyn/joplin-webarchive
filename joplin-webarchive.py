#!/usr/bin/python
# -*- coding: utf-8 -*-

import yaml
import hashlib
import json
import re
import httpx
import datetime
import sys
import argparse
import tempfile
import os
from urllib.parse import urlparse

from joplin_api import JoplinApiSync
from datetime import timedelta

#
# TODO (patches are welcomed) :
#   - I should add a way to « normalize » URLs, even better if a configurable basis
#     (like blogspot.fr == blogspot.com, youtu.be == youtube.com and so on).
#   - Improve silent / verbosity levels <- lot of improvement already done !
#   - Complete MIME type management (But I don’t think it’s worth the needed work at the moment)
#   - Learn (real) Python instead of publishing badly written scripts. 
#   - Joplin API up to 1.7.11 has an image size limitation ! See https://github.com/laurent22/joplin/pull/4660
#     This is a problem for storing webshots as images. Code a work-around ?
#

def print_msg (level, s):
    if not silent and verbosity >= level :
         print(s)

def generate_uuid(s):
    print_msg(9, f"generate_uuid({s})")
    uuid_salt = yaml_config['uuid_salt']
    string_to_hash = s + uuid_salt
    hash_object = hashlib.md5(str(string_to_hash).encode('utf-8'))
    return( hash_object.hexdigest() )

def get_cache_folder_uuid(folder_name):
    # First try to find folder
    search = joplin.search(folder_name, item_type='folder')
    y = json.loads(search.text)
    for i in y['items']:
        if( not i['parent_id'] and i['title'] == folder_name ):
            return(i['id'])

    # We should have returned a valid id, but in case no valid answers
    print( f"No valid folder by name '{folder_name}' found ?!")
    exit()
   
def is_in_cache_folder(folder_uuid, forbidden):
    if( folder_uuid == forbidden ):
        return ( True )
    
    try:
        parent = joplin.get_folder(folder_uuid)
    except httpx.HTTPStatusError as exc:
#        print(f"Error response {exc.response.status_code} while requesting {exc.request.url!r}.")
        if( exc.response.status_code == 404 ):    
#            print("I will ignore this ressource")
            return ( True )
        else:
            raise Exception("WTF happened ?")
            
    j = json.loads(parent.text)
    if( j['parent_id'] ):
        return(is_in_cache_folder(j['parent_id'], forbidden))
        
    # No parent_id, means it’s at the root, so congrats !
    return ( False )

#
# Get the folder UUID, create the folder if needed
#

def get_subfolder(folder_name):
    global cache_folder_uuid 
    
    if( folder_name[-1] == "/" ):
        folder_name = folder_name[:-1]   
      
    parent_uuid = cache_folder_uuid
      
    a = folder_name.split("/")

    for f in a:
        valid_found = False
        # First try to find folder
        search = joplin.search(f, item_type='folder', )
        y = json.loads(search.text)

        for i in y['items']:
            if( i['parent_id'] == parent_uuid and i['title'] == f ):
                valid_found = True
                parent_uuid = i['id']   
    
        if ( not valid_found):
            # If it does not exist, create it
            joplin.create_folder(folder=f, parent_id=parent_uuid)

            # Now we should have a valid answer
            search = joplin.search(f, item_type='folder')
            y = json.loads(search.text)

            for i in y['items']:
                if( i['parent_id'] == parent_uuid and i['title'] == f ):
                   valid_found = True 
                   parent_uuid = i['id']

            # If not, raise exception
            if( not valid_found) :
                raise Exception("Could not create (apparently) non-existent folder " + f)

    # Last iteration => we have finally found the folder uuid
    return parent_uuid



def get_cache_folder_name (url):
#    print("===== New URL :", url, "=====")
    o = urlparse(url)
#    print(o)
 
    if( not o.port ):
        if( o.scheme == "ftp" ):
            port = 21        
        if( o.scheme == "http" ):
            port = 80       
        if( o.scheme == "https" ):
            port = 443
    else:
        port = o.port

    netlocme = o.netloc.split(":")    
    netloc = netlocme[0]    
    
    # Order them in reverse order
    a = netloc.split(".")
    reverse_path = ""
    for i in a:
        reverse_path = i + "/" + reverse_path
    
    folder = o.scheme + "-" + str(port) + "/" + reverse_path
    return(folder)

#
# Check if an url has specifics
#

def get_conf_for(url):
    # Copy the defaults
    conf = yaml_content.copy()
    del conf['specifics']
    
    # Should we copy the other parameters ?
    for sp in yaml_content['specifics']:
        # print("Try on", url, "specifics : ", sp, ) 
        try:
            regex_test = re.findall(sp['regex'], url)
        except:
            print("Warn: No valid regex for specifics ?", sp)
            regex_test = False
            
        if regex_test:
            print_msg(4, "Regex matches "  + sp['regex'] + " : " + url)
            for i in sp.keys():
                conf[i] = sp[i]

    # Also store its url and its associated uuid in conf structure
    conf['uuid'] = generate_uuid(url)        
    conf['url'] = url

    # No cache_refresh means... refresh every 100 years (or 36500 days more precisely). 
    if not "cache_refresh" in conf or conf['cache_refresh'] == 0 :
        conf['cache_refresh'] = 36500
        
    return conf
        
#
# new_link
#
# Called each time the Markdown parser finds a new link. 
#

def new_link( conf ):
    # These values should be filled by Markdown parser !
    uuid = conf['uuid']
    url = conf['url']
    source_uuid = conf['src_uuid']
    title = conf['src_title']
    
    now = datetime.datetime.now()

    # Does the note exist ?
    if uuid in update_ts:   
        print_msg( 3, f"new_link() : new link to a known URL : {uuid} - {url } (taken from {source_uuid} - {title})" )
        # On a new link, check if early refresh is set
        if "force_refresh_on_new_link_after" in conf :
            if type( update_ts[uuid]["last"] ) != str  :
                print_msg ( 3, f"Checking if {url} is older than {conf['force_refresh_on_new_link_after']} days in update_ts")
            
                ts = update_ts[uuid]["last"] + timedelta(days=conf['force_refresh_on_new_link_after'])
                if ts < now :
                    print_msg (3, "Forcing update for {url} on {ts}")
                    update_ts[uuid]['next'] = ts

    else:
        # It seems this page is newly cached, so create the folders and version page 
        print_msg( 3, f"new_link() : new URL : {uuid} - {url } (taken from {source_uuid} - {title})" )

        # Track the page.
        update_ts[uuid] = { }
        update_ts[uuid]['url'] = url
        update_ts[uuid]['last'] = "never"
        update_ts[uuid]['next'] = now
        update_ts[uuid]['internal_link'] = "[Cache for " + url + "](:/" + source_uuid + ")"

        if not dry_run :
            # Generate the folder, if needed (and get its uuid)
            folder_name = get_cache_folder_name(url)
            folder_uuid = get_subfolder(folder_name)
                
            print_msg(4, f"Creating note {uuid} in folder {folder_uuid} for url {url}" )
            now = datetime.datetime.now()
            d1 = now.strftime("%d/%m/%Y")
            note_txt = "First seen on " + d1 + " in page [" + title + "](:/" + source_uuid + ")\n\n"
            note_txt = note_txt + f"**joplin-webarchive**: Updates every {conf['cache_refresh']} days\n"
            note_txt = note_txt + "*(You may edit this value to refresh more often, it is automatically recognized)*\n\n"
            try:
                joplin.create_note( "Cache for " + url, note_txt, folder_uuid, id=uuid )
            except httpx.HTTPStatusError as exc:
                # print(f"Error response {exc.response.status_code} while requesting {exc.request.url!r}.")
                if( exc.response.status_code == 500 ):
                    # Did the note already exists ?
                    try:
                        internal_note = joplin.get_note( uuid )   
                    except httpx.HTTPStatusError as exc2:
                        print(f"Error response {exc2.response.status_code} while requesting {exc2.request.url!r}.")
                        if( exc2.response.status_code != 404 ):
                            print(f"Error response {exc2.response.status_code} while requesting {exc2.request.url!r}.")
                            print("Did not get an error 404 when trying to create new internal note ?!")
                            raise Exception("Can’t store create new note with ID " + uuid + " and such note does not already exist !")
                    else:
                        # Happpened due to crash / exit while coding. Should not happen for end user
                        print("WARN note for url " + url + " id=" + uuid + " already exists !")           
                 
    return uuid
   
def check_string_for_url(s, source_uuid, title):
    # What you want to able to parse : https://github.com/adam-p/markdown-here/wiki/Markdown-Cheatsheet
    print_msg(4, f"Running check_string_for_url( {s}, {source_uuid}, {title} ) ..." )
    
    # Capture a triple, with (string_before, url, string_after)
    triple_re = "(.*?)(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+#]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+)(.*)"
    triple_test = re.findall(triple_re, s)
    # print(triple_test)

    # No url found, quickly return the whole string.
    if( not triple_test ):
        return s

    before = triple_test[0][0]
    raw_url = triple_test[0][1]
    after = triple_test[0][2]

    # URL between parenthesis ?? Like ([Google](http://www.google.com/)) 
    if len(before) > 0 and len(raw_url) > 0 and before[-1] == "(" and raw_url[-1] == ")" :
        print_msg(6, f"URL between paranthesis ? : {raw_url}" )
        raw_url = raw_url[0:-1]
        after = ")" + after

    url = raw_url

    space_re = "[ \t]*"        
    # Regex which indicates it is a no cache URL 
    nocache_re = "[\(\[]+[ \t]*no\s*cache[ \t]*[\)\]]+"
    # Regex which indicates the cache already exists 
    cache_exists_re = "[\(\[]+\s*\[\s*cache[ \t]*\]\(:/[0-9a-fA-F]{32}(?:\#\S*)?\)\s*[\)\]]"
    # Checks if cache already exists by combining previous regex
    cache_re = "^[ \t]*(" + nocache_re + "|" + cache_exists_re + ")"

    # Some « urls » are in fact comments of another URL : [http://www.google.fr](http://www.google.fr) 
    # So, catch them !
    if len(before) > 0 and len(url) > 0 and before[-1] == "[" :
        print_msg(6, "Url is a comment of another URL ?" )
        end_comment_re = "(^.+?][ \t]*)(.*)$"
        end_comment_test = re.findall(end_comment_re, url)
        # If last caracter before url is [ and « url » contains ], parse recursively after the ]
        if end_comment_test and len(end_comment_test[0][1]) > 0:
            print_msg(6, "Url is a comment of another URL ? Confirmed !!!" )
            fils = check_string_for_url(end_comment_test[0][1] + triple_test[0][2], source_uuid, title )
            return ( before + end_comment_test[0][0] + fils )
            
    # Urls between < and > are wrongly taken, so correct here.
    if( len(before) > 0 and len(url) > 0 and before[-1] == "<" and url[-1] == ">" ):
        # print("Wrong assignement", triple_test, "url to cut :", url)
        url = url[0:-1]

    # Urls between ( and ) are wrongly taken, so correct here.
    if( len(before) > 0 and len(url) > 0 and before[-1] == "(" and url[-1] == ")" ):
        # print("Wrong assignement", triple_test, "url to cut :", url)
        url = url[0:-1]

    # Same with ). and ]. as they do happen often
    if( len(before) > 0 and len(url) > 0 and before[-1] == "<" and url[-2] == ">" and (url[-1] == "." or url[-1] == ",") ):
        # print("Wrong assignement", triple_test, "url to cut :", url)
        url = url[0:-2]
    if( len(before) > 0 and len(url) > 0 and before[-1] == "(" and url[-2] == ")" and (url[-1] == "." or url[-1] == ",") ):
        # print("Wrong assignement", triple_test, "url to cut :", url)
        url = url[0:-2]

    # Normalize URL. Big TODO in fact.
    # => http://slashdot.org and http://slashdot.org/ are the same !

    print_msg(3, f"check_string_for_url() : Found URL in {title} : {url}")

    # Remove text after # (URL fragment), not exactly part of URL.
    fragment_re = "(.*)#(.*)"
    fragment_test = re.findall(fragment_re, url)   
    if( fragment_test ) :
        url = fragment_test[0][0]

    # If URL without path ... (+ 
    try:
        o = urlparse(url)
    except:
        print ("Can’t parse URL " + url + " - Will parsing ignore and parse son")
        fils = check_string_for_url(triple_test[0][2], source_uuid, title)
        return( before + raw_url + fils )

    if not o.path:
        url = url + "/"
   
    print_msg(4, f"Normalized URL : {url}")

    # Get conf for this url, we might need to ignore it !
    conf = get_conf_for(url)
    # Store source and title also in this structure
    conf['src_uuid'] = source_uuid
    conf['src_title'] = title
    # By default, cache everything - create adequate structure
    if not "nocache" in conf:
        conf['nocache'] = False
        
    # Markdown « inline-style link with title » syntax used here
    inline_after_re = '([ \t]+".+?"\))(.*)'
    inline_after_test = re.findall(inline_after_re, after)
    inline_before_re = "\[.*?\]\($"
    inline_before_test = re.findall(inline_before_re, before)

    # Is it Markdown « inline-style link with title » syntax ?
    # In that case, keep separated inline markdown part and the unparsed part.
    if( inline_after_test and inline_before_test ):
        inline_md = inline_after_test[0][0] 
        fils_unparsed = inline_after_test[0][1]
    else:
        inline_md = ""
        fils_unparsed = after
    
    # Ok, now is this URL tagged with an empty [cache] tag ??
    cache_create_re = "^" + space_re + "([\[\(]" + space_re + "cache" + space_re + "[\]\)])(.*)$"  
    cache_create_test = re.findall( cache_create_re, fils_unparsed )  
    if cache_create_test :   
        # Debug
        print_msg( 5, "Got force cache tag : " + cache_create_test[0][0] )
        print_msg( 5, "We keep this part : " + cache_create_test[0][1] )
        fils = check_string_for_url(cache_create_test[0][1], source_uuid, title)
        # Force caching !
        conf['nocache'] = False
    else :
        fils = check_string_for_url(fils_unparsed, source_uuid, title)

    # If the cache for this link already exists, just ignore this link
    print_msg( 4, f"Gonna regex {fils_unparsed} for cache with {cache_re}")
    cache_test = re.findall(cache_re, fils_unparsed)
    if cache_test or conf['nocache'] :
        # In that case, force refresh of this URL
        return( before + raw_url + inline_md + fils )
        
    # We have parsed a new link, so check or create internal structure (update_ts and associated notes)
    new_link( conf )
    
    return( before + raw_url + inline_md + " ([cache](:/" + conf['uuid'] + "))" + fils )

#
# Parse a markdown note
#
# I know it’s useless to pass title and uuid of note, but it’s needed in case we want to 
# create a new note (=in case of new url)
#
# return modified note in case of modification
# False otherwise
#

def parse_markdown(body, title, uuid):
    print_msg(1, f"parse_markdown( **body**, {title}, {uuid})")
    modified = False
    out_string = ""

    # Is there at least smthg which look like there ? (We could save time)
    if not re.findall("(https?|ftps?)://", body):
        return False 
    
    for s in body.splitlines():
        # Empty strings : no reason to parse
        if s != "":
            s2 = check_string_for_url(s, uuid, title)
        else:
            s2 = s

        if s != s2:
            # Make debug appear 
            print_msg(1, "-" + s)
            print_msg(1, "+" + s2)
            modified = True
        out_string += s2 + "\n"

    if modified:
        return out_string
    
    return False

#
# Check if a note for new URLs.
#
#    returns true if it was the case
#            false otherwise
#
# At the moment, only supports markdown language
#
    
def check_note_for_new_urls(uuid):
    print_msg(0, f"check_note_for_new_urls({uuid})")
    
    r = joplin.get_note(uuid)
    j = json.loads(r.text)

    # Is it markdown ?
    if j['markup_language'] == 1:
        out = parse_markdown(j['body'], j['title'], uuid)
        if out != False and not dry_run:
            joplin.update_note( uuid, j['title'], out, j['parent_id'] )
            # Quickly save database changes... We may gain some speed by avoiding doing it each time, 
            # but at the risk of more corruption in case of failure.
            update_update_ts()
            return True
        return False

    # Is it HTML ?
    if j['markup_language'] == 2:
        print("Can’t parse note", j['title'], "as HTML not supported (yet ?)")
        return False
    
    # Unknown markup_language, not documented yet
    print (j)
    print ("Unknown markup_language == ", j['markup_language'] )
    print ("Not documented as of 15th march 2021 : https://joplinapp.org/api/references/rest_api/")
    print ("So not doing anything for note", j['title'])
    return False
    
#
# Update expiration dates
# 

def update_update_ts ():
    if not dry_run :
        joplin.update_note( yaml_config['update_ts_guid'], yaml_config['update_ts_title'], "### When shall we refresh ?\n### Automatically updated, edit at your own risks\n\n" + yaml.dump(update_ts), cache_folder_uuid )  

def get_update_ts () :
    # Get expiration dates
    exp = joplin.get_note( yaml_config['update_ts_guid'] )  
    j = json.loads(exp.text)
    try:
        update_ts = yaml.load( j['body'], Loader=yaml.FullLoader)   
    except:
        print("Error while parsing note", yaml_config['update_ts_title'], "as YAML content")
        print("Did you try to edit this note ? Is it still valid YAML ?")
        exit()
    return(update_ts)

#
# Run an update on note modified in last x days
#
# Looks like API returns only max 100 answer on search. So we use an ugly-patched for of python-api here
# 

def update_notes(days):
    # List of ID we will update after search is done
    todos = [ ]

    has_more = True
    page = 1
    limit = 100
    
    while has_more:
        print_msg(5, f"update_notes() : query page {page}")
        search = joplin.search_paged("updated:day-" + days, page, limit, item_type='note')
        j = json.loads(search.text)

        has_more = j['has_more']
        page = page + 1
    
        for i in j['items']:
            if( not is_in_cache_folder(i['parent_id'], cache_folder_uuid)):
                print_msg(3, "Found note : " + i['id'] + " - " + i['title'] )
                todos.append(i['id'])

    # Now that we have the list of item to parse, do it !
    for i in todos:
        status = check_note_for_new_urls(i)

#
# Did we edit the cache target page ?
#
# At the moment, only recognizes "**joplin-webarchive**: Updates every 36500 days" syntax
#

def check_cache_target_page(uuid):
    print_msg( 0, f"check_cache_target_page({uuid})")
    
    # Get parent_id
    api_out = joplin.get_note( uuid )
    note_json = json.loads(api_out.text)     

    # The only recognized regex ...
    space_re = "[ \t]*"        
    cache_refresh_re = "\*\*joplin-webarchive\*\*"+space_re+":" +space_re+" [Uu]pdates?"+space_re+"every"+space_re+"([0-9]+)"+space_re+"days?"
    cache_refresh_test = re.findall( cache_refresh_re, note_json['body'] )  

    if (cache_refresh_test) :
        print_msg(2, f"check_cache_target_page(): cache_refresh for « {note_json['title']} » : {cache_refresh_test[0]}")
        
        if type( update_ts[uuid]["last"] ) != str : 
            update_ts[uuid]['next'] = update_ts[uuid]["last"] + timedelta(days=int(cache_refresh_test[0]))    
    else:
        print_msg(4, f"check_cache_target_page(): no update parameter found for  « {note_json['title']} »") 
            
#
# If we changed the update frequency in a note, we need to update our internal values.
#
# Looks like API returns only max 100 answer on search. So we use an ugly-patched for of python-api here
# 

def update_cache_target_page(days):
    # List of ID we will update after search is done
    todos = [ ]

    has_more = True
    page = 1
    limit = 100
    
    while has_more:
        print_msg(5, f"update_cache_target_page() : guery page {page}")
        search = joplin.search_paged("Cache for updated:day-" + days, page, limit, item_type='note')
        j = json.loads(search.text)

        has_more = j['has_more']
        page = page + 1
    
        # Only check our internal folder
        for i in j['items']:
            if i['id'] in update_ts :
                print_msg(3, "Updated cache page : " + i['id'] + " - " + i['title'] )
                todos.append(i['id'])

    # Now that we have the list of item to parse, do it !
    for i in todos:
        status = check_cache_target_page(i)



#
# Parse all notes (should be used just after first start)
#
# Looks like API returns only max 100 answer on search.  
# also on folders, so... 
#
# Best Ideas : do not do it recursively, if we want to parse all notes, just parse all notes updated on last 100 years...
#
# No way to use pagination with (python module) joplin-api 1.6.0
#   See : https://joplinapp.org/api/references/rest_api/#pagination
#
# Ok, I did ugly patching.
#
# Sorry, I wish it was any better
# 

def recursive_parse():
    # First all folders
    r = joplin.get_folders()
    j = json.loads(r.text)
 
    # Only keep folders outside of cache_folder_uuid
    for i in j['items']:
        # Only parse folders outside of cache folder
        if not is_in_cache_folder(i['id'], cache_folder_uuid) :
            print(i)
            
            r = joplin.get_folders_notes( i['id'] )
            j2 = json.loads(r.text)
            
            for i2 in j2['items']:
                check_note_for_new_urls( i2['id'] )


#
# First run : create internal structures.
# and parse all notes.
#

def first_run():
    try:
        internal_note = joplin.get_note( yaml_config['internal_note_guid'] )   
    
    except httpx.HTTPStatusError as exc:
        if( exc.response.status_code != 404 ):
            print(f"Error response {exc.response.status_code} while requesting {exc.request.url!r}.")
            print("Did not get an error 404 when trying to create new internal note ?!")
            print("Are you sure this is first run ?")
            exit()
    else:
        print("Did not get an error 404 when trying to create new internal note ?!")
        print("Are you sure this is first run ?")
        exit()
        
    print("First run. I have checked internal note", yaml_config['internal_note_guid'], "does not exist yet !")

    # First creates the cache folder 
    api_out = joplin.create_folder(folder=yaml_config['cache_folder'])
    j = json.loads(api_out.text)    
    cache_folder_uuid = j['id']

    # Create internal note with (empty) update_ts (as we will need to call update_note in the future)
    update_ts = { }
    joplin.create_note(yaml_config['update_ts_title'], yaml.dump(update_ts), cache_folder_uuid, id=yaml_config['update_ts_guid'] ) 
     
    # Take defaults from config.yaml
    yaml_content = yaml_config.copy()
    # Save folder value here too.
    yaml_content['cache_folder_uuid'] = cache_folder_uuid

    # But we don’t want people to modify this parameters as they are sensitive / ignored.
    del yaml_content['uuid_salt']
    del yaml_content['joplin_token']
    del yaml_content['internal_note_title']
    del yaml_content['internal_note_guid']
    del yaml_content['update_ts_guid']
    del yaml_content['update_ts_title']

    new_note_txt  = "### This is an internal YAML note for joplin-webarchive !\n"
    new_note_txt += "### Only use YAML Syntax here !\n"
    new_note_txt += "### This note won’t be updated by joplin-webarchive, so any comments you add should be left intact !\n\n"
    new_note_txt += yaml.dump(yaml_content)

    joplin.create_note(yaml_config['internal_note_title'], new_note_txt, cache_folder_uuid, id=yaml_config['internal_note_guid'] )

    # Verbose message instead of forcing recursive parse
    print("Internal notes created, maybe you now want to fill the database ?")
    print("Try running", sys.argv[0], "--recursive")

    exit()

# Function for nth fibonacci 
# number - Space Optimisataion
# Taking 1st two fibonacci numbers as 0 and 1
 
def fibonacci(n):
    a = 0
    b = 1
     
    if n < 0:
        print("Incorrect input")
         
    elif n == 0:
        return 0
       
    elif n == 1:
        return b
    
    else:
        for i in range(1, n):
            c = a + b
            a = b
            b = c
        return b

#
# Run a command with some debug / logging (or not in silent mode)
# 

def run_cmd(cmd): 
    if silent and ( cmd.find(">") == -1 ): 
        cmd = cmd + " > /dev/null 2> /dev/null"

    print_msg(0, f"Running command {cmd} ...")
    os.system(cmd)

#
# Run an update on an url
#
                
def update_url(index):
    url = update_ts[index]['url']

    print_msg(0, f"update_url({index}) : {url}" )

    now = datetime.datetime.now()
    day_str = now.strftime("%d/%m/%Y")

    # Get conf for this url
    conf = get_conf_for(url)

    # Get parent_id
    try:
        api_out = joplin.get_note( index )
        note_json = json.loads(api_out.text) 
        parent_id = note_json['parent_id']
    except:
        if dry_run :
            print_msg( 0, f"Could not get note {index}. Is it a new one created in this session ?")
            print_msg( 0,  "As we are in dry_run mode, if it corresponds to a new URL, that’s pretty normal.")
            parent_id = "undefined"
        else :
            # Fatal error
            print( f"Could not access note {index} for {url}...")
            exit()

    # message which will be added to the archive note
    msg = ""

    # 
    # First check HTTP status and content/type
    #
    is_down = False
    
    try:
        r = httpx.get(update_ts[index]['url'])
    except:
        print_msg(1, f"Got httpx exception while catching {url}")
        is_down = True

    # Bad HTTP Error Codes :
    if not is_down and r.status_code > 400 :
        print_msg(1, f"Got error {r.status_code} while catching {url}")
        is_down = True
    
    if is_down :
        print_msg(0, f"{url} seems down. So postponing scraping ...")
        if "errors" in update_ts[index] :
        	count = update_ts[index]["errors"] + 1
        else :
            count = 1
        days = fibonacci( count )
        print_msg(1, f"Error count : {count} - fibo result {days} days ; will try again in {days} days")
        update_ts[index]["errors"] = count
        update_ts[index]["next"] = now + timedelta( days=days )
        return False

    # Some debug in verbosity mode
    print_msg(2, f"{update_ts[index]['url']} returned this Content-Type: {r.headers['Content-Type']}")
    print_msg(3, f"parent_id: {parent_id}, id: {index}")

    # For not handled yet MIME types...
    use_general_handler = True
    as_ressource = True
    ext = ".unknown"
    
    # Handle images
    if r.headers['Content-Type'] == "image/jpeg" or r.headers['Content-Type'] == "image/gif" or r.headers['Content-Type'] == "image/png"  :
        use_general_handler = False
        
        img_format = r.headers['Content-Type'][6:]
        # print(f"Image format {img_format}")
        fd, output_fn = tempfile.mkstemp(suffix = f'.{img_format}')
        # print("Writing to", output_fn)
        os.write(fd, r.content)
        os.close(fd)
        
        title = f"{update_ts[index]['url']} ({r.headers['Content-Type']}) on {day_str}"
        if not dry_run :
            api_out = joplin.create_resource( output_fn, title=title )
            j = json.loads(api_out.text)
            
        msg += f"[{img_format}](:/{j['id']}) "
        
        # Do we also generate thumbnails ? (requires imagemagick)
        if conf['create_thumbnail'] :
            fd2, thumb_fn = tempfile.mkstemp(suffix = f'.{img_format}')
            os.close(fd2)
            os.system(f"convert {output_fn} -resize {conf['thumbnail_size']} {thumb_fn}")
            title = f"Thumb for {update_ts[index]['url']} on {day_str}"
            if not dry_run :
                api_out = joplin.create_resource( thumb_fn, title=title )
                j = json.loads(api_out.text)

            os.remove(thumb_fn)
            
            msg = f"![Thumb](:/{j['id']}) " + msg
        
        os.remove(output_fn)
       
    # Handle HTML
    if r.headers['Content-Type'][0:9] == "text/html" :
        #
        # HTML format is the most complex format
        # 
        use_general_handler = False
    
        # print(r)
        # print(r.content)

        # Store Markdown
        if conf['store_md'] :
            # Write to a temporary file
            fd, html_fn = tempfile.mkstemp(suffix = '.html')
            os.write(fd, r.content)
            os.close(fd)

            # Get a temporary Markdown file
            fd, md_fn = tempfile.mkstemp(suffix = '.md')
            os.close(fd)
            
            # Run pandoc
            run_cmd(f"pandoc -f html -t markdown_github -o {md_fn} {html_fn}") 
            # Check file not empty
            if os.stat(md_fn).st_size > 0 :
                title = f"Markdown (pandoc converted) for {update_ts[index]['url']} on {day_str}"
                f = open( md_fn, "r")
                dump_txt = f.read()
                f.close()
               
                if not dry_run :
                    try:
                        api_out = joplin.create_note( title, dump_txt, parent_id )
                        j = json.loads(api_out.text)
                        msg = msg + f"[Markdown](:/{j['id']}) "
                    except:
                        print("Got exception when storing Markdown content.... Will force text scraper !") 
                        conf['store_txt'] = True

            os.remove(md_fn)
            os.remove(html_fn)
            
        
        # Store lynx dump
        if conf['store_txt'] :
            fd, lynx_fn = tempfile.mkstemp(suffix = '.txt')
            os.close(fd)
            # Run lynx
            run_cmd(f"lynx -dump '{update_ts[index]['url']}' > {lynx_fn}") 
            # Check file not empty
            if os.stat(lynx_fn).st_size > 0 :
                title = f"Text (lynx -dump) for {update_ts[index]['url']} on {day_str}"
                f = open( lynx_fn, "r")
                dump_txt = f.read()
                f.close()
                
                if not dry_run :
                    api_out = joplin.create_note( title, dump_txt, parent_id )
                    j = json.loads(api_out.text)
                msg = msg + f"[TXT](:/{j['id']}) "

            os.remove(lynx_fn)

        # Store 
        if conf['store_png']  or conf['create_thumbnail'] :
            # Write to a temporary file
            fd, png_fn = tempfile.mkstemp(suffix = '.cutycapt.png')
            os.write(fd, r.content)
            os.close(fd)

            # Run cuttycapt
            run_cmd(f"xvfb-run -a --server-args='-screen 0, 1280x768x24' timeout 180 cutycapt --min-width=1250 --url='{update_ts[index]['url']}' --out='{png_fn}'")
            
            if conf['create_thumbnail']  and os.stat(png_fn).st_size > 0  :
                fd2, thumb_fn = tempfile.mkstemp(suffix = '.thumb.png')
                os.close(fd2)
                run_cmd(f"convert '{png_fn}' -resize {conf['thumbnail_size']} '{thumb_fn}'")
                title = f"Thumb for {update_ts[index]['url']} on {day_str}"
                if not dry_run and os.stat(thumb_fn).st_size > 0 :
                    try:
                        api_out = joplin.create_resource( thumb_fn, title=title )
                        j = json.loads(api_out.text)
                        msg = f"![Thumb](:/{j['id']}) " + msg                   
                    except:
                        pass
                os.remove(thumb_fn)

            if conf['store_png'] and os.stat(png_fn).st_size > 0  : 
                title = f"Image Capture for {update_ts[index]['url']} on {day_str}"
                if not dry_run :
                    try:
                        api_out = joplin.create_resource( png_fn, title=title )
                        j = json.loads(api_out.text)
                        msg = msg + f"[PNG](:/{j['id']}) "                      
                    except:
                        pass
   
            os.remove(png_fn)
            
        # Store a PDF copy
        if conf['store_pdf'] :
            # Write to a temporary file
            fd, pdf_fn = tempfile.mkstemp(suffix = '.pdf')
            os.write(fd, r.content)
            os.close(fd)

            # Run wkhtmltopdf
            run_cmd(f"xvfb-run -a --server-args='-screen 0, 1280x768x24' timeout 180 wkhtmltopdf '{update_ts[index]['url']}' '{pdf_fn}'")

            if os.stat(pdf_fn).st_size > 0  : 
                title = f"PDF Capture for {update_ts[index]['url']} on {day_str}"
                if not dry_run :
                    api_out = joplin.create_resource( pdf_fn, title=title )
                    j = json.loads(api_out.text)
                    msg = msg + f"[PDF](:/{j['id']}) "               
            
            os.remove(pdf_fn)

        # Keep videos ?
        if conf['store_videos'] :
            # Create a temporary directory for youtube-DL to 
            vid_path = tempfile.mkdtemp()
            print_msg(4, "Temporary path for youtube-dl : {vid_path}")

            # Run youtube-dl with storage there
            run_cmd(f"youtube-dl -q -o '{vid_path}/%(title)s-%(id)s.%(ext)s' '{update_ts[index]['url']}'")

            # Now add all the output to Joplin
            i = 1
            for short_fn in os.listdir(vid_path) :
                full_fn = vid_path + "/" + short_fn
                print_msg (4, "After running youtube-dl, found file: {full_fn}")

                title = f"{short_fn} from {update_ts[index]['url']} on {day_str}"
                if not dry_run :
                    api_out = joplin.create_resource( full_fn, title=title )
                    j = json.loads(api_out.text)
                        
                msg = msg + f"[Video {i}](:/{j['id']}) "               
                i += 1

                os.remove(full_fn)

            os.rmdir(vid_path)

    # Handle other text formats
    if r.headers['Content-Type'][0:9] != "text/html" and r.headers['Content-Type'][0:5] == "text/" :
        txt_format = r.headers['Content-Type'][5:]
        as_ressource = False
        use_general_handler = True
        
        # Plain text
        if r.headers['Content-Type'] == "text/plain" :
            ext = ".txt"

        # Should diff be ressources or text ? 
        # good question...
        if r.headers['Content-Type'] == "text/x-diff" :
            ext = ".diff"
            as_ressource = True

    # XML ressource. Same question : should they be ressources or text ?
    if r.headers['Content-Type'] == "application/xml" :
        ext = ".xml"
        use_general_handler = True
        as_ressource = False
   
    # PDF
    if r.headers['Content-Type'] == "application/pdf" :
        ext = ".pdf"
        use_general_handler = True
        as_ressource = True
      
    # Now that we sorted MIME types
    if use_general_handler :
        if as_ressource :
            fd, output_fn = tempfile.mkstemp(suffix = ext)
            os.write(fd, r.content)
            os.close(fd)
            
            title = f"{update_ts[index]['url']} ({r.headers['Content-Type']}) on {day_str}"
            if not dry_run :
                api_out = joplin.create_resource( output_fn, title=title )
                j = json.loads(api_out.text)

            os.remove(output_fn)
            
            msg += f"[{r.headers['Content-Type']}](:/{j['id']}) "            

        else:    
            title = f"{update_ts[index]['url']} ({r.headers['Content-Type']}) on {day_str}"
            if not dry_run :
                api_out = joplin.create_note(title, r.text, parent_id )
                j = json.loads(api_out.text)
                
            msg += f"[{r.headers['Content-Type']}](:/{j['id']}) "

    print_msg(2, f"Will add to cache note : {msg}" )
   
    #
    # Update note
    #
    
    if not dry_run and msg != "" :
        # Log redirects
        # httpx will follow HTTP redirects. I didn’t found a way to catch easily all of them... 
        # so I decided no to log the last redirect, not the chain.
        if r.history:
            msg += f"<small>(Redirects to {r.url} ; chain : {r.history})</small>"
            print_msg(2, f"Will in fact add to cache note : {msg}" )            
            
        api_out = joplin.update_note( index, note_json['title'], note_json['body'] + f"\n- **{day_str}** " + msg, note_json['parent_id'] )  
        # j = json.loads(api_out.text)
        # print(j)

        # Find when next update should happen.
        space_re = "[ \t]*"        
        cache_refresh_re = "\*\*joplin-webarchive\*\*"+space_re+":" +space_re+" [Uu]pdates?"+space_re+"every"+space_re+"([0-9]+)"+space_re+"days?"
        cache_refresh_test = re.findall( cache_refresh_re, note_json['body'] )  
        if (cache_refresh_test) :
            print_msg(3, f"Parsed cache_refresh for « {note_json['title']} » on page cache : {cache_refresh_test[0]}")
            cache_refresh = int(cache_refresh_test[0])
        else:
            cache_refresh = conf['cache_refresh']        
        print_msg( 2, f"Next update for {url} : in {cache_refresh} days" )

        # Update correct timestamps        
        update_ts[index]["last"] = now            
        update_ts[index]["next"] = now + timedelta( days=cache_refresh )

        # Reset error index.
        if "errors" in update_ts[index] :
            del update_ts[index]["errors"]
        
        # We edited note.
        return True

    # Note not edited.
    return False

#
# Check update_ts list for new urls
#

def update_urls():
    now = datetime.datetime.now()
    
    for i in update_ts:
        if update_ts[i]['next'] < now :
            modified = update_url(i)

            # Quickly save database changes... We may gain some speed by avoiding doing it each time, 
            # but at the risk of more corruption in case of failure.
            update_update_ts()
          


# 
# Handle command line arguments.
#

parser = argparse.ArgumentParser()
group = parser.add_mutually_exclusive_group()
parser.add_argument("-d", "--dry-run", help="Do not modify existing notes", action="store_true") 
parser.add_argument("--silent", help="Do not run any output, except huge (blocking) fails", action="store_true")
parser.add_argument("--verbose", "-v", action='count', default=0)
group.add_argument("--days", help="How many days to look up in history ?", action="store")
group.add_argument("--first", help="Run first run (create internal notes) and recursively parse all notes", action="store_true")
group.add_argument("--recursive", help="Recursively parse all notes. (default : only on notes updated on last 7 days) -- NOT PROPERLY WORKING ", action="store_true")
args = parser.parse_args()

dry_run = args.dry_run

# Verbosity switches
verbosity = args.verbose
silent = args.silent

# By default, run on last 7 days
if not args.days:
    args.days = "7"

#
# Open config.yaml to get Joplin Token
# 

yaml_file = open("config.yaml", 'r')
yaml_config = yaml.load(yaml_file, Loader=yaml.FullLoader)
joplin_token=yaml_config['joplin_token']

joplin = JoplinApiSync(token=joplin_token)

# Check if Joplin is running - in order to print a nice message error
try:
    api_out = joplin.ping()
except:
    print( "Could not run joplin.ping()... Are you sure Joplin is running ?! Is the clipper service activated ? Is the token OK ?")
    exit()

# First run ?
if args.first:
    first_run()
    exit


#
# Getting Joplin internal YAML configuration
#


try:
    internal_note = joplin.get_note( yaml_config['internal_note_guid'] )   
    
except httpx.HTTPStatusError as exc:
    # print(f"Error response {exc.response.status_code} while requesting {exc.request.url!r}.")
    if( exc.response.status_code == 404 ):
        # Create note on first run
        print("We had an 404 error while accessing note", yaml_config['internal_note_guid'], " !!!")
        print("First run ?")
        print("Try running", sys.argv[0], "--first")
        exit()
        
    else:
        print ("Unexpected error while getting Internal note")
        exit()

else:
    j = json.loads(internal_note.text)
    yaml_content = yaml.load(j['body'], Loader=yaml.FullLoader)

cache_folder_uuid = get_cache_folder_uuid(yaml_config['cache_folder'])

update_ts = get_update_ts()


# just debug on my draft note here
#check_note_for_new_urls("ac3af830cb9c4c0aba58813e3f05235b")
#update_update_ts()
#exit()
                

# Recursive run instead of update ? 
# (not working as of march 2021, due to limitation on Python Joplin API I didn’t try to get around) 
if ( args.recursive ):
    recursive_parse()

else:
    update_notes(args.days)
    update_cache_target_page(args.days)

# Now update the URLs
update_urls()

# Update our internal database before leaving
update_update_ts()



