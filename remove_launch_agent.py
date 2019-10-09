#!/System/Library/Frameworks/Python.framework/Versions/Current/bin/python
# -*- coding: utf-8 -*-
"""
remove_launch_agent.py
Removes LaunchAgents based on their identifier.

Copyright 2019 Glynn Lane (primalcurve)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

###############################################################################
#-----------------------------------------------------------------------------#
# Import Statements
#-----------------------------------------------------------------------------#
###############################################################################

# Remove any other detected paths to prevent issues with incompatible versions
# of PyObjC or other modules.
import sys
for index, path in enumerate(sys.path):
    if path[1:6] == "Users" or path[1:8] == "Library":
        sys.path.pop(index)

import argparse
import datetime
import logging
import logging.handlers
import os
import plistlib
import re
import subprocess


###############################################################################
#-----------------------------------------------------------------------------#
# Globals
#-----------------------------------------------------------------------------#
###############################################################################

EPOCH_AS_FILETIME = 116444736000000000
HUNDREDS_OF_NANOSECONDS = 10000000

# Binary paths
# Set global constants
LAUNCHCTL = ("/bin/launchctl")

# Logging Info
SCRIPT_NAME = ("remove_launch_agent")
R_DOMAIN = "com.github.primalcurve"
LIBRARY_SUPPORT = ("/Library/Application Support/")
LIBRARY_LOGS = ("/Library/Logs/")
LIBRARY_LAUNCHAGENTS = ("/Library/LaunchAgents/")

# Logging Config
# This must happen within the global namespace to allow access to the logger
# from any function or class.
logger = logging.getLogger(SCRIPT_NAME)
logger.setLevel(logging.DEBUG)

## Some initial setup
### Create a reverse domain name for the program folders
LONG_R_DOMAIN = R_DOMAIN + "." + SCRIPT_NAME
### Create paths to the logs and cache.
LOG_PARENT_DIR = os.path.join(
    LIBRARY_LOGS, R_DOMAIN, LONG_R_DOMAIN)
SCRIPT_CACHE = os.path.join(
    LIBRARY_SUPPORT, R_DOMAIN, LONG_R_DOMAIN)
### Make the directories if they do not exist.
if not os.path.exists(LOG_PARENT_DIR):
    os.makedirs(LOG_PARENT_DIR)
if not os.path.exists(SCRIPT_CACHE):
    os.makedirs(SCRIPT_CACHE)
### Create the name of the log file for the logger.
LOG_FILE = os.path.join(LOG_PARENT_DIR, LONG_R_DOMAIN + ".log")

## Configure the logger object.
### logging Formatters
easy_formatter = logging.Formatter("%(message)s")
file_formatter = logging.Formatter(
    "%(asctime)s|func:%(funcName)s|" +
    "line:%(lineno)s|%(message)s")
### Defining the different Log StreamHandlers
log_stderr = logging.StreamHandler()
#### Rotate the log file every 1 day 5 times before deleting.
log_logfile = logging.handlers.TimedRotatingFileHandler(
    LOG_FILE, when="D", interval=1, backupCount=5)
### Defining different log levels for each StreamHandler
#### Only log INFO and above logging events to stderr
log_stderr.setLevel(logging.INFO)
#### Log all messages with DEBUG and above to the logfile.
log_logfile.setLevel(logging.DEBUG)
### Add formatters to logging Handlers.
log_stderr.setFormatter(easy_formatter)
log_logfile.setFormatter(file_formatter)
### Add all of the handlers to this logging instance:
logger.addHandler(log_stderr)
logger.addHandler(log_logfile)


###############################################################################
#-----------------------------------------------------------------------------#
# Custom Classes and Functions
#-----------------------------------------------------------------------------#
###############################################################################


class LocalUser(object):
    """Object that provides attributes and methods for working with user
    accounts on machines.
    """
    def __init__(self, shortname):
        """Basic Initialization. Nothing runs until start_script is called.
        """
        self.shortname = shortname
        dscl_cmd = ["/usr/bin/dscl", "-plist", ".",
                    "-read", "/Users/" + self.shortname]
        self._dscl_plist = self._run_dscl(dscl_cmd)
        if self._dscl_plist:
            self._populate_user_info()

    def _run_dscl(self, dscl_cmd):
        try:
            return subprocess.check_output(dscl_cmd)
        except subprocess.CalledProcessError:
            return False

    def _populate_user_info(self):
        self._dscl_dict = plistlib.readPlistFromString(self._dscl_plist)
        for key, value in self._dscl_dict.iteritems():
            process_key_values(self, key, value)

    def run_as_me(self, cmd, get_output=True):
        logger.debug("Running requested command as %s: %s" %
                     (self.real_name, " ".join(cmd)))
        if get_output:
            return self._run_as_me(cmd)
        else:
            results = self._run_as_me(cmd)
            if not results[0] and not results[1]:
                return False
            if results[1] and results.returncode:
                return False
            else:
                return True

    def _run_as_me(self, cmd):
        # Run command as the user using subprocess's preexec_fun method.
        try:
            return subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                preexec_fn=self._demote()).communicate()
        except subprocess.CalledProcessError:
            return (False, False)

    def _demote(self):
        def result():
            logger.debug("Starting Demotion")
            os.setgid(self.primary_group_id)
            os.setuid(self.unique_id)
            logger.debug('Finished Demotion')
        return result


def process_key_values(instance_object, key, value):
    """Processes key/value pairs from class methods to clean them up
    as programatically as possible.
    Args:
        (obj) object: Instance of an object to modify its __dict__
        (str) key: Raw key from object method. This is probably in some
                   weird case.
        (str) value: Raw value from object method.
    Returns:
        None: Instances are modified in place.
    """
    logger.debug("Received raw key: " + key)
    ignore_list = [
        "user_certificate", "cached_groups", "shadow_hash_data",
        "cached_auth_policy", "password", "preserved_attributes",
        "linked_identity", "account_policy_data", "mcx_settings",
        "mcx_flags", "original_authentication_authority",
        "apple_meta_node_location"]
    are_lists = []
    lower_case = ["uid"]
    title_case = [
        "display_name", "first_name", "given_name"]
    home_folders = ["smb_home", "original_smb_home"]
    windows_timestamps = [
        "smb_password_last_set", "bad_password_time", "last_logon",
        "last_logon_timestamp", ]
    # Convert pascalCase keys to pascal_case keys as these will be converted
    # into attributes.
    try:
        key = fix_case(key.split(":")[1])
    except IndexError:
        key = fix_case(key)

    # Key Modification.
    if key == "objectclass" or key == "object_class":
        key = "object_class"
    # Some keys from dscl that have embedded images and other large
    # chunks of data.
    elif key[:9] == "_writers_":
        return
    # Other keys we don't need.
    elif key in ignore_list:
        return

    # Value Modification.
    # Convert lists with single members into one component.
    if isinstance(value, list) and len(value) == 1:
        value = value[0]

    # Convert email addresses to lower_case.
    if "@" in value or key in lower_case:
        logger.debug("Converting %s to %s" % (value, value.lower()))
        value = value.lower()
    # Convert names that may be in ALL CAPS to Title Case.
    elif key in title_case:
        logger.debug("Converting %s to %s" % (value, value.title()))
        value = value.title()
    # Special case where multiple values will be returned with the same key.
    elif key in are_lists:
        logger.debug(
            "Appending list Attribute: %s with Value: %s" %
            (key, str(value)))
        # Try to set the key directly,
        try:
            instance_object.__dict__[key].append(value)
        # If the key doesn't exist yet, create it.
        except KeyError:
            instance_object.__dict__.update({key: [value]})
        return
    # Specific keys:
    # Convert Windows timestamp to seconds since epoch
    # and then to a datetime object.
    elif key in windows_timestamps:
        value = datetime.datetime.utcfromtimestamp(
            (int(value) - EPOCH_AS_FILETIME) / HUNDREDS_OF_NANOSECONDS)
        logger.debug("Converted Windows time stamp to datetime: %s" % (value))
    elif key == "member_of":
        value = [
            v.split("=", 1)[1].split(",", 1)[0] for v in value]
    # Convert SMBHome from Windows formatted paths to macOS formatted.
    elif key in home_folders:
        logger.debug("Converting %s to %s" % (value, smb_home_fix(value)))
        value = smb_home_fix(value)
    # Try to convert any possible date into a datetime object.
    try:
        value = datetime.datetime.strptime(value, "%Y-%m-%d")
        logger.debug("Converted %s to datetime: %s" % (key, value))
    except ValueError:
        pass
    except TypeError:
        pass
    # Try to convert any possible integer into an integer object.
    try:
        value = int(value)
        logger.debug("Converted %s to integer: %s" % (key, value))
    except ValueError:
        pass
    except TypeError:
        pass
    # Try to convert phone numbers to a more easily-read version.
    try:
        code, num = value.split("/")
        value = ("(%s) %s" % (code, num))
        logger.debug("Converted %s to phone number: %s" % (key, value))
    except ValueError:
        pass
    except AttributeError:
        pass
    # Now that conversion is complete, add the value to the object.
    logger.debug(
        "Adding Attribute: %s with Value: %s" % (key, str(value)))
    instance_object.__dict__.update({key: value})


def fix_case(pascal_case):
    # Use regex substitution to make pascalCase pascal_case
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', pascal_case)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def smb_home_fix(smb_home):
    return (
        "smb://" + "/".join([s for s in smb_home.split("\\") if s]).lower())


def get_mobile_users():
    """Return a list of users in OD with OriginalNodeName
    Args:
        None
    Returns:
        (list) All users in OD with OriginalNodeName
    """
    # Get string from dscl.
    dscl_cmd = ["/usr/bin/dscl", "-plist", ".",
                "-list", "/Users", "OriginalNodeName"]
    try:
        cmd_out = subprocess.check_output(dscl_cmd).strip()
    except subprocess.CalledProcessError:
        cmd_out = ""

    # Return list not including anyone in the explicit ignored_users list
    ignored_users = ["admin", "root", "daemon", "guest", "nobody"]
    return [LocalUser(u.split(" ")[0]) for u in cmd_out.splitlines()
            if u.split(" ")[0] not in ignored_users]


def get_arguments():
    # Returns the results of the argparse module reading argv.
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-name", required=True,
                        help="Name of the LaunchAgent without .plist")
    parser.add_argument("--agent-domain", default="system",
                        help="LaunchAgent domain. See 'man launchctl' " +
                        "for more information.")
    parser.add_argument("--agent-directory", default="/Library/LaunchAgents",
                        help="Directory containing LaunchAgents")
    # Skip unknown arguments.
    arguments, _ = parser.parse_known_args()
    logger.info(
        "Parsed Parameters: agent-name: " + str(arguments.agent_name) +
        " agent-directory: " + str(arguments.agent_directory))
    return arguments


###############################################################################
#-----------------------------------------------------------------------------#
# Main Function
#-----------------------------------------------------------------------------#
###############################################################################
def main():
    """Main function"""
    # Get argparse parameters.
    arguments = get_arguments()

    # Build launchctl targets (domain/service-targets) for the LaunchAgent
    if arguments.agent_domain.lower() == "system":
        root_user = LocalUser("root")
        root_user.domain_target = ("system")
        root_user.service_target = ("system/" + arguments.agent_name)
        root_user.launch_agent_file = os.path.join(
            "/Library/LaunchAgents", arguments.agent_name + ".plist")
        mobile_users = [root_user]
    else:
        mobile_users = get_mobile_users()
        for user in mobile_users:
            user.domain_target = (
                arguments.agent_domain + "/" + user.unique_id)
            user.service_target = (
                user.domain_target + "/" + arguments.agent_name)
            user.launch_agent_file = os.path.join(
                user.nfs_home_directory, "Library/LaunchAgents/",
                arguments.agent_name + ".plist")

    for user in mobile_users:
        # Read existing LaunchAgent. LaunchAgents are represented as plists in
        # macOS. We will use plistlib to read it. This will convert the
        # LaunchAgent into a Python dictionary.
        if os.path.exists(user.launch_agent_file):
            logger.debug("Reading contents of : " + user.launch_agent_file)
            with open(user.launch_agent_file, "r") as la_file:
                launch_agent_dict = plistlib.readPlist(la_file)
        else:
            launch_agent_dict = dict()

        # If the LaunchAgent is designed to run in the loginwindow domain,
        # then we will make sure our service target is correct.
        session_types = launch_agent_dict.get("LimitLoadToSessionType", [])
        if "LoginWindow" in session_types:
            logger.debug("Changing domain_target to loginwindow.")
            arguments.agent_domain = ("loginwindow")
            user.service_target = ("loginwindow/" + arguments.agent_name)

        # Tear down the LaunchAgent:
        cmd_list = [[LAUNCHCTL, "kill", "-15", user.service_target],
                    [LAUNCHCTL, "bootout", user.service_target],
                    [LAUNCHCTL, "disable", user.service_target]]

        # Run the launchctl commands, but don't pipe their output as that will
        # create a lot of noise in the logs.
        for cmd in cmd_list:
            logger.debug("Running: " + str(cmd))
            try:
                subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                ).communicate()
            except subprocess.CalledProcessError as e:
                logger.debug("Caught CalledProcessError: " + str(e))

        if os.path.exists(user.launch_agent_file):
            logger.debug("Deleting: " + str(user.launch_agent_file))
            os.unlink(user.launch_agent_file)

    logger.debug("Finished processing LaunchAgent removal.")
    sys.exit(0)


if __name__ == "__main__":
    main()
