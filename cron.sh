#!/bin/bash

# Absolute path to this script. /home/user/bin/foo.sh
SCRIPT=$(readlink -f $0)
# Absolute path this script is in. /home/user/bin
SCRIPTPATH=`dirname $SCRIPT`
cd $SCRIPTPATH

temp_file=$(mktemp)
joplin server start > $temp_file &
# It seems to take some time to start. We’re not in a hurry, that’s fine.
sleep 30


joplin sync
python3.7 /home/airmax/joplin-webarchive/joplin-webarchive.py -vvv
joplin sync

joplin server stop

cat $temp_file
rm $temp_file

