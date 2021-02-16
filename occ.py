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

ME = socket.gethostname()
TMPL_FAILURE = ME + """ failed to reconfigure due to the following error(s):

Return code: %d
Error message: %s

Please fix this error before service can resume.
"""


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
                if oncommit:
                    print("Found a matching payload, preparing to execute command '%s':" % oncommit)
                    if isinstance(oncommit, str):
                        try:
                            subprocess.check_output((oncommit,), stderr=subprocess.STDOUT)
                            print("Command executed successfully")
                        except subprocess.CalledProcessError as e:
                            print("on-commit command failed with exit code %d!" % e.returncode)
                            blamelist = subdata.get('blamelist')
                            blamesubject = subdata.get('blamesubject', "OCC execution failure")
                            if blamelist:
                                print("Sending error details to %s" % blamelist)
                                asfpy.messaging.mail(recipient=blamelist, subject=blamesubject, message=TMPL_FAILURE % (e.returncode, e.output))
                        except FileNotFoundError:
                            print("Could not find script to execute; file not found!")
                            blamelist = subdata.get('blamelist')
                            blamesubject = subdata.get('blamesubject', "OCC execution failure")
                            if blamelist:
                                print("Sending error details to %s" % blamelist)
                                asfpy.messaging.mail(recipient=blamelist, subject=blamesubject,
                                                     message=TMPL_FAILURE % (-1, "Script file %s not found" % oncommit))


def main():
    print("Loading occ.yaml")
    cfg = yaml.safe_load(open('occ.yaml'))
    print("Connecting to pyPubSub at %s" % cfg['pubsub']['url'])
    pypubsub = asfpy.pubsub.Listener(cfg['pubsub']['url'])
    print("Connected, listening for events :-)")
    pypubsub.attach(lambda x: parse_commit(x, cfg), auth=(cfg['pubsub']['user'], cfg['pubsub']['pass']), raw=True)


if __name__ == "__main__":
    main()
