# Copyright (c) 2016, Robert Escriva
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of this project nor the names of its contributors may
#       be used to endorse or promote products derived from this software
#       without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import base64
import datetime
import hmac
import json
import re
import subprocess
import tempfile
import threading

import flask
from flask import request

app = flask.Flask(__name__)

SECRET = b'XXX'
OUTPUT = '/home/rescrv/5300-dns'
ZONE = '/etc/nsd/bigdata.systems.zone'

class OutputFile:

    def __init__(self, fname):
        self.fout = open(fname, 'a')
        self.mtx = threading.Lock()

    def append(self, obj):
        obj = json.dumps(obj)
        with self.mtx:
            self.fout.write(obj + '\n')
            self.fout.flush()

out = OutputFile(OUTPUT)

@app.route('/')
def index():
    return '''<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <link rel="stylesheet" href="http://yui.yahooapis.com/pure/0.6.0/pure-min.css">
    <title>5300 DNS</title>
  </head>
  <body>
    <div style="width: 80%; max-height: 80%; margin: auto">
      <form class="pure-form pure-form-stacked" role="form" action="/update" method="POST">
        <fieldset>
          <legend>Update DNS</legend>
          <label for="netid">netid</label>
          <input id="netid" name="netid" type="text" placeholder="xxx123">
          <label for="password">password</label>
          <input id="password" name="password" type="password" placeholder="password">
          <label for="hosts">hosts</label>
          <input id="hosts" name="hosts" type="text" placeholder="x,y,z">
          <button type="submit" class="pure-button pure-button-primary">Update</button>
        </fieldset>
      </form>
    </div>
  </body>
</html>
'''

def is_valid_hostname(hostname):
    if len(hostname) > 255:
        return False
    if hostname[-1] == ".":
        hostname = hostname[:-1] # strip exactly one dot from the right, if present
    allowed = re.compile("(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
    return all(allowed.match(x) for x in hostname.split("."))

def password(netid):
    H = hmac.new(SECRET)
    H.update(netid.encode('ascii'))
    x = H.digest()
    return base64.urlsafe_b64encode(x).rstrip(b'=').decode('ascii')

@app.route('/update', methods=['POST'])
def update():
    netid = request.form.get('netid', None)
    passw = request.form.get('password', None)
    hosts = request.form.get('hosts', None)
    if password(netid) != passw:
        return 'wrong netid/password combo'
    hosts = [h.strip() for h in hosts.split(',')]
    for h in hosts:
        if not is_valid_hostname(h):
            return '%r is not a valid hostname' % h
    if len(hosts) > 20:
        return "you don't need more than 20 hosts"
    out.append({'netid': netid, 'hosts': hosts,
                'time': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')})
    return '''update successfull:<br/>
{0}<br/>
these hosts can take up to 10 minutes to take effect
'''.format('<br/>\n'.join(['server%d.%s.bigdata.systems => %s' % (idx, netid, h)
                      for (idx, h) in enumerate(hosts)]))

def main_web():
    app.debug = False
    app.run('0.0.0.0', 8000, threaded=True, use_reloader=True)

ZONE = '''$ORIGIN bigdata.systems.
$TTL 60

@       3600    SOA     ns1.bigdata.systems. hostmaster.bigdata.systems. (
                        SERIALXXXX      ; serial
                        1800            ; refresh
                        7200            ; retry
                        1209600         ; expire
                        3600 )          ; negative

                NS      ns1.bigdata.systems.
                NS      ns2.bigdata.systems.

                MX      0 mail.bigdata.systems.

@       3600    A       128.84.155.96

a.ns    3600    A       128.84.155.96
ns1     3600    A       128.84.155.96
ns2     3600    A       128.84.155.97
mail    3600    CNAME	rye.rescrv.net.
'''

def get_serial():
    f = open(ZONE)
    for line in f:
        if 'serial' in line:
            try:
                return int([x.strip() for x in line.split(' ') if x][0])
            except:
                pass
    return 2016040712

def main_zone():
    hostnames = {}
    for line in open(OUTPUT):
        obj = json.loads(line.strip())
        hostnames[obj['netid']] = obj['hosts']
    zone = ZONE
    serial = get_serial()
    zone = zone.replace('SERIALXXXX', str(serial + 1))
    for netid, hosts in sorted(hostnames.items()):
        for idx, h in enumerate(hosts):
            if h and h[-1] == '.':
                h = h[:-1]
            zone += 'server%d.%s\t\tCNAME\t%s.\n' % (idx,netid,h)
    print(zone)

def main_pass():
    import sys
    print(password(sys.argv[2]))

def main_mail():
    import sys
    netid = sys.argv[2]
    message = '''To: {0}@cornell.edu
From: John Doe <john.doe@example.org>
Subject:  Your bigdata.systems password

username: {0}
password: {1}

Please see the post on piazza for more details:
https://piazza.com/class/ijx05p9ypp817b?cid=182
'''.format(netid, password(netid))
    fout = tempfile.NamedTemporaryFile()
    fout.write(message.encode('utf8'))
    fout.flush()
    fout.seek(0)
    subprocess.check_call(('msmtpq', netid + '@cornell.edu'),
                          stdin=fout)

if __name__ == '__main__':
    import sys
    if sys.argv[1] in ('www', 'web'):
        main_web()
    if sys.argv[1] == 'zone':
        main_zone()
    if sys.argv[1] == 'pass':
        main_pass()
    if sys.argv[1] == 'mail':
        main_mail()
