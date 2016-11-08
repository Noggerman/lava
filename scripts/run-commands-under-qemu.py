#!/usr/bin/python
# import re
import os
from os.path import abspath, join, basename
# import socket
import sys
import tempfile
import subprocess32
import shutil
import time
import pipes
import json
#from colorama import colorama.Fore, colorama.Back, colorama.Style
import colorama
#from pexpect import pexpect.spawn, pexpect.fdpexpect
import pexpect
import psutil

debug = True


def dprint(msg):
    if debug:
        print msg

def progress(msg):
    print colorama.Fore.RED + msg + colorama.Fore.RESET

if len(sys.argv) < 2:
    print >>sys.stderr, "Usage: python project.json"
    sys.exit(1)

def run_remote(remote_host, cmd):
    progress("Running {} on {}".format(cmd, remote_host))
    subprocess32.check_call(["ssh", remote_host]+cmd)

project_file = abspath(sys.argv[1])
# get first input file and run it

project = json.load(open(project_file, "r"))

# *** Required json fields
# list of intended inputs to executable
assert 'inputs' in project
# path to qemu exec (correct guest)
assert 'qemu' in project
# name of snapshot from which to revert which will be booted & logged in as root?
assert 'snapshot' in project
# same directory as in add_queries.sh, under which will be the build
assert 'directory' in project
# command line to run the target program (already instrumented with taint and attack queries)
assert 'command' in project
# path to guest qcow
assert 'qcow' in project
# name of project
assert 'name' in project
# path to tarfile for target (original source)
assert 'tarfile' in project
# if needed, what to set LD_LIBRARY_PATH to
assert 'library_path' in project

# path to project on host
assert 'install_dir' in project

#############
# compile on laredo-26 omitting for now . . .
# r_host = project['buildhost']
# progress("Building {}".format(test_src, r_host))
#cmd = "cd {}".format(sourcedir)
#cmd += "&&" + project['configure']
#cmd += "&&" + project['make']
#cmd += "&&" + project['install']
# run_remote(r_host, cmd)

##############

# progress("Entering {}.".format(project['directory']))
# os.chdir(os.path.join(project['directory'], project['name']))

input_file = project['inputs'][0]
input_file_base = basename(input_file)
tar_files = subprocess32.check_output(['tar', 'tf', project['tarfile']])
#sourcedir = project['source_dir']
installdir = project['install_dir']

print

panda_log_base_dir = project['directory']
if not os.path.isdir(panda_log_base_dir):
    os.makedirs(panda_log_base_dir)

# creates a ith directory for each det log starting at 0 if there are no number
# folders
num_dir = len(filter(lambda s: s.isdigit(), os.listdir(panda_log_base_dir)))
panda_log_loc = os.path.join(panda_log_base_dir, "{}/".format(num_dir))
if os.path.isdir(panda_log_loc):
    shutil.rmtree(panda_log_loc)
os.mkdir(panda_log_loc)
progress("Creating panda log directory {}...".format(panda_log_loc))


panda_log_name = os.path.join(panda_log_loc, project['name'] + "_" + input_file_base)

# prepping lava-install by copying necessary input files into it
#installdir = join(sourcedir, 'lava-install')
#print "inputfile: {} inputfilebase: {} sourcedir: {}".format(input_file, input_file_base, sourcedir)
if not os.path.exists(join(installdir, input_file_base)):
    shutil.copy(input_file,      join(installdir, input_file_base))
#shutil.copy(test_input_file, join(installdir, basename(test_input_file)))
#shutil.copy(test_exec,       join(installdir, basename(test_exec)))

#iso_base = "/nas/ulrich/dwarf_tshark_capture2/wireshark-1.2.1"
#isoname = '{}-{}.iso'.format(iso_base, input_file_base)
##isoname = 'tmp.iso'
isoname = os.path.join(panda_log_loc, project['name']) + ".iso"
progress("Creaing ISO {}...".format(isoname))

with open(os.devnull, "w") as DEVNULL:
    subprocess32.check_call(['genisoimage', '-RJ', '-max-iso9660-filenames', '-o', isoname, installdir], stderr=DEVNULL)

tempdir = tempfile.mkdtemp()
# Find open VNC port.
connections = psutil.net_connections(kind='tcp')
vnc_ports = filter(lambda x : x >= 5900 and x < 6000, [c.laddr[1] for c in connections])
vnc_displays = set([p - 5900 for p in vnc_ports])
new_vnc_display = None
for i in range(10, 100):
    if i not in vnc_displays:
        new_vnc_display = i
        break
if new_vnc_display == None:
    progress("Couldn't find VNC display!")
    sys.exit(1)

monitor_path = os.path.join(tempdir, 'monitor')
serial_path = os.path.join(tempdir, 'serial')
qemu_args = [project['qcow'], '-loadvm', project['snapshot'],
        '-monitor', 'unix:' + monitor_path + ',server,nowait',
        '-serial', 'unix:' + serial_path + ',server,nowait',
        '-vnc', ':' + str(new_vnc_display)]

print ' '.join(qemu_args)

print
progress("Running qemu with args:")
print project['qemu'], " ".join(qemu_args)
print

os.mkfifo(monitor_path)
os.mkfifo(serial_path)
qemu = pexpect.spawn(project['qemu'], qemu_args)
qemu.logfile = sys.stdout
time.sleep(1)

monitor = pexpect.spawn("socat", ["stdin", "unix-connect:" + monitor_path])
monitor.logfile = open(os.path.join(tempdir, 'monitor.txt'), 'w')
console = pexpect.spawn("socat", ["stdin", "unix-connect:" + serial_path])
console.logfile = open(os.path.join(tempdir, 'console.txt'), 'w')

def run_monitor(cmd):
    if debug:
        print "monitor cmd: [%s]" % cmd
    print colorama.Style.BRIGHT + "(qemu)" + colorama.Style.RESET_ALL,
    monitor.sendline(cmd)
    monitor.expect_exact("(qemu)")
    print monitor.before.partition("\r\n")[2]

def run_console(cmd, expectation="root@debian-i386:~"):
    if debug:
        print "console cmd: [%s]" % cmd
    print colorama.Style.BRIGHT + "root@debian-i386:~#" + colorama.Style.RESET_ALL,
    console.sendline(cmd)
    try:
        console.expect_exact(expectation)
    except pexpect.TIMEOUT:
        print console.before
        raise

    print console.before.partition("\n")[2]

def run_console_timeout(cmd, expectation="root@debian-i386:~", timeout=-1):
    if debug:
        print "console cmd: [%s]" % cmd
    print colorama.Style.BRIGHT + "root@debian-i386:~#" + colorama.Style.RESET_ALL,
    console.sendline(cmd)
    try:
        console.expect_exact(expectation, timeout=timeout)
    except pexpect.TIMEOUT:
        print console.before
        raise

    print console.before.partition("\n")[2]


# Make sure monitor/console are in right state.
monitor.expect_exact("(qemu)")
console.sendline("\n\n")
console.expect_exact("root@debian-i386:~#")

progress("Inserting CD...")
run_monitor("change ide1-cd0 {}".format(isoname))
time.sleep(1)
run_console("mkdir -p {}".format(installdir))
time.sleep(1)
# Make sure cdrom didn't automount
run_console("umount /dev/cdrom")
time.sleep(1)
# Make sure guest path mirrors host path
run_console("mount /dev/cdrom {}".format(installdir))
time.sleep(1)
run_console("ls {}/lib".format(installdir))
run_console("df")
run_console("df")
run_console("df")

progress("Beginning recording queries...")

run_monitor("begin_record {}".format(panda_log_name))

time.sleep(1)

progress("Running command inside guest. Panda log to: {}".format(panda_log_name))
input_file_guest = join(installdir, input_file_base)
expectation = project['expect'] if 'expect' in project else "root@debian-i386:~"

env = project['env'] if 'env' in project else {}
if project['library_path'] != "":
    env['LD_LIBRARY_PATH'] = project['library_path'].format(install_dir=installdir)

env_string = " ".join(["{}={}".format(pipes.quote(k), pipes.quote(env[k])) for k in env])

# run command
progress("Running command " + project['command'] + " on guest")
run_console(env_string + " " + project['command'].format(
    install_dir=installdir,
    input_file=input_file_guest), expectation)

time.sleep(1)

progress("Ending recording...")
run_monitor("end_record")

monitor.sendline("quit")
shutil.rmtree(tempdir)
#os.remove(isoname)

