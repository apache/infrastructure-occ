#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""On-Commit-Commands - a simple pubsub client that runs a command on commit activity"""

import asfpy.messaging
import asfpy.pubsub
import yaml
import subprocess
import socket
import pwd
import sys
import os
import getpass

ME = socket.gethostname()
TMPL_FAILURE = ME + """ failed to reconfigure due to the following error(s):

Return code: %d
Error message: %s

Please fix this error before service can resume.
"""


def run_as(username=getpass.getuser(), args=()):
    """ Run a command as a specific user """
    pw_record = pwd.getpwnam(username)
    user_name = pw_record.pw_name
    user_uid = pw_record.pw_uid
    user_gid = pw_record.pw_gid
    env = os.environ.copy()
    env['HOME'] = pw_record.pw_dir
    env['LOGNAME'] = user_name
    env['PWD'] = os.getcwd()
    env['USER'] = username
    print("Running command %s as user %s..." % (" ".join(args), username))
    process = subprocess.Popen(
        args, preexec_fn=change_user(user_uid, user_gid), cwd=os.getcwd(), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    result = process.communicate(timeout=30)
    if process.returncode == 0:
        return
    else:
        raise subprocess.CalledProcessError(returncode=process.returncode, cmd=args, output=result[0].decode('utf-8'))


def change_user(user_uid, user_gid):
    def result():
        os.setgid(user_gid)
        os.setuid(user_uid)
    return result


def parse_commit(payload, config):
    if 'stillalive' in payload:  # Ping, Pong...
        return
    for subkey, subdata in config.get('subscriptions', {}).items():
        sub_topics = subdata.get('topics').split('/')
        sub_changedir = subdata.get('changedir')
        if all(topic in payload['pubsub_topics'] for topic in sub_topics):
            matches = True
            if sub_changedir:  # If we require changes within a certain dir in the repo..
                matches = False
                changes = payload.get('commit', {}).get('changed')
                for change in changes.keys():
                    if change.startswith(sub_changedir):
                        matches = True
                        break
            if matches:
                oncommit = subdata.get('oncommit')
                runas = subdata.get('runas', getpass.getuser())
                if oncommit:
                    print("Found a matching payload, preparing to execute command '%s':" % oncommit)
                    if isinstance(oncommit, str):
                        blamelist = subdata.get('blamelist')
                        blamesubject = subdata.get('blamesubject', "OCC execution failure")
                        try:
                            run_as(runas, (oncommit,))
                            print("Command executed successfully")
                        except subprocess.CalledProcessError as e:
                            print("on-commit command failed with exit code %d!" % e.returncode)
                            if blamelist:
                                print("Sending error details to %s" % blamelist)
                                asfpy.messaging.mail(recipient=blamelist, subject=blamesubject, message=TMPL_FAILURE % (e.returncode, e.output))
                        except FileNotFoundError:
                            print("Could not find script to execute; file not found!")
                            if blamelist:
                                print("Sending error details to %s" % blamelist)
                                asfpy.messaging.mail(recipient=blamelist, subject=blamesubject,
                                                     message=TMPL_FAILURE % (-1, "Script file %s not found" % oncommit))
                        except KeyError:
                            print("Could not execute command as %s - user not found??" % runas)
                            asfpy.messaging.mail(recipient=blamelist, subject=blamesubject,
                                                 message=TMPL_FAILURE % (-1, "Username %s not found" % runas))
                        except subprocess.SubprocessError:
                            print("Subprocess error - likely could not change to user %s" % runas)
                            asfpy.messaging.mail(recipient=blamelist, subject=blamesubject,
                                                 message=TMPL_FAILURE % (-1, "Subprocess error while trying to run as user %s" % runas))

def main():
    print("Loading occ.yaml")
    cfg = yaml.safe_load(open('occ.yaml'))
    print("Connecting to pyPubSub at %s" % cfg['pubsub']['url'])
    pypubsub = asfpy.pubsub.Listener(cfg['pubsub']['url'])
    print("Connected, listening for events :-)")
    pypubsub.attach(lambda x: parse_commit(x, cfg), auth=(cfg['pubsub']['user'], cfg['pubsub']['pass']), raw=True)


if __name__ == "__main__":
    main()
