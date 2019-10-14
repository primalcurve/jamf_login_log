#!/System/Library/Frameworks/Python.framework/Versions/Current/bin/python
# -*- coding: utf-8 -*-
"""
jamf_login_log.py
Creates a LaunchAgent that is scoped to run in the loginwindow domain. This
LaunchAgent then runs a script that spawns a GUI over the Login Window that
displays information about the current state of the device.

Copyright 2019 Glynn Lane (primalcurve)

Based on LoginLog: https://github.com/MagerValp/LoginLog
Copyright 2013-2016 Per Olofsson, University of Gothenburg

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
import os
import pwd
import sys
import plistlib


# Set global constants
LAUNCHCTL = ("/bin/launchctl")
system_python = ("/System/Library/Frameworks/Python.framework/" +
                 "Versions/Current/Resources/Python.app/Contents/MacOS/Python")
library_support = ("/Library/Application Support/")
library_logs = ("/Library/Logs/")
library_launchagents = ("/Library/LaunchAgents/")
launch_agent_label = ("com.github.primalcurve.jamf_login_log")
launch_agent_file = os.path.join(
    library_launchagents, launch_agent_label + ".plist")
launch_agent_support = os.path.join(
    library_support, launch_agent_label)
launch_agent_out_path = os.path.join(
    library_logs, launch_agent_label + ".log")
log_script_file = os.path.join(
    library_support, launch_agent_label + ".py")

# Represent the LaunchAgent as a Python dictionary.
launch_agent_dict = dict(
    Label=launch_agent_label,
    ProgramArguments=[
        system_python,
        log_script_file
        ],
    LimitLoadToSessionType=["LoginWindow"],
    RunAtLoad=True,
    KeepAlive=False,
    StandardOutPath=launch_agent_out_path,
    StandardErrorPath=launch_agent_out_path
)

# Get the uid and gid of root (should always be 0 and 0), but it doesn't
# hurt to have it check every time. We will need this in a couple of places
# within this script.
uid = pwd.getpwnam("root").pw_uid
gid = pwd.getpwnam("root").pw_gid

# Read existing LaunchAgent. LaunchAgents are represented as plists in macOS
# Therefore we will use plistlib to read it. This will convert the
# LaunchAgent into a Python dictionary, just like our object above.
if os.path.exists(launch_agent_file):
    with open(launch_agent_file, 'rb') as fp:
        existing_launch_agent = plistlib.readPlist(fp)
    print("LaunchAgent already exists. Checking it against master LD.")
else:
    existing_launch_agent = None
    print("LaunchAgent does not yet exist. Will create.")

# If the LaunchAgents do not match, then we will re-write it.
if existing_launch_agent != launch_agent_dict:
    # Set existing_launch_agent to New so that if the LaunchAgent is updated,
    # the old one is properly booted out.
    existing_launch_agent = "New"
    print("LaunchAgent does not exist or does not match master. Creating.")
    # Write the LaunchAgent:
    with open(launch_agent_file, 'wb') as fp:
        plistlib.writePlist(launch_agent_dict, fp)

    # Make sure the LaunchAgent has the correct permissions:
    # Set the ownership.
    os.lchown(launch_agent_file, uid, gid)
    # Set permissions:
    os.chmod(launch_agent_file, 0o644)

else:
    print("Existing LaunchAgent matches master. Continuing.")

#-----------------------
# Create the script
#-----------------------

log_script = ("""
#!/System/Library/Frameworks/Python.framework/Versions/Current/Resources/Python.app/Contents/MacOS/Python

import re
import objc
import Cocoa
import subprocess
# Limit Foundation and AppKit imports to speed up loading.
from Foundation import (
    NSLog,
    NSMutableArray,
    NSObject,
    NSString,
    NSTimer,
    NSUTF8StringEncoding,
)
from AppKit import (
    NSAnimationContext,
    NSApp,
    NSApplication,
    NSBundle,
    NSButton,
    NSCenterTextAlignment,
    NSColor,
    NSFileHandle,
    NSFont,
    NSLayoutConstraintOrientationVertical,
    NSLeftTextAlignment,
    NSRightTextAlignment,
    NSRoundedBezelStyle,
    NSScreen,
    NSScreenSaverWindowLevel,
    NSScrollView,
    NSScrollerStyleOverlay,
    NSStatusWindowLevel,
    NSTableColumn,
    NSTableView,
    NSTextField,
    NSTextView,
    NSUserDefaults,
    NSWindow,
    NSWindowController
)
from SystemConfiguration import (
    SCPreferencesGetValue,
    SCPreferencesCreate,
    SCDynamicStoreCreate,
    SCDynamicStoreCopyValue,
    SCNetworkInterfaceCopyAll,
    SCNetworkInterfaceGetBSDName,
    SCNetworkInterfaceGetLocalizedDisplayName,
    SCNetworkInterfaceGetHardwareAddressString
)

from PyObjCTools import AppHelper


class JamfLogButton(NSButton):
    # Set some defaults for the buttons so their configurations do not need
    # to be hand-coded every time.
    button_size = (180.0, 26.0)

    def initWithOptions(self, title, position, target=None,
                        key_equivalent=None, action=None):
        # Call the super class (NSButton)
        self = objc.super(JamfLogButton, self).initWithFrame_(
            (position, self.button_size))
        if self is None:
            return None

        self.setBezelStyle_(NSRoundedBezelStyle)
        self.setEnabled_(True)
        self.setTitle_(title)
        if target:
            self.setTarget_(target)
        if key_equivalent:
            self.setKeyEquivalent_(key_equivalent)
        if action:
            self.setAction_(action)

        return self


class JamfLogTable(NSTableView):
    def init(self):
        # Call the super class (NSTableView)
        self = objc.super(JamfLogTable, self).init()
        if self is None:
            return None

        # Set defaults.
        self.contentHuggingPriorityForOrientation_(
            NSLayoutConstraintOrientationVertical)
        self.setUsesAlternatingRowBackgroundColors_(True)
        self.setFont_(NSFont.userFixedPitchFontOfSize_(12))
        self.setHeaderView_(None)

        return self


class JamfLogScrollView(NSScrollView):
    def initWithFrame_(self, frame):
        # Call the super class (NSScrollView)
        self = objc.super(JamfLogScrollView, self).initWithFrame_(frame)
        if self is None:
            return None

        # Set defaults.
        self.setBorderType_(2)
        self.setHasVerticalScroller_(True)
        self.setScrollerStyle_(NSScrollerStyleOverlay)

        return self


class JamfLogTextField(NSTextField):
    def initWithOptions(self, text, frame):
        # Call the super class (NSTextField)
        self = objc.super(JamfLogTextField, self).initWithFrame_(frame)
        if self is None:
            return None

        # Set defaults.
        self.setStringValue_(
            NSString.stringWithString_(text))
        self.setBezeled_(False)
        self.setDrawsBackground_(False)
        self.setSelectable_(False)
        self.setFont_(NSFont.systemFontOfSize_(12))
        self.setAlignment_(NSCenterTextAlignment)

        return self


class JamfLogTextView(NSTextView):
    def initWithOptions(self, text, frame):
        # Call the super class (NSTextField)
        self = objc.super(JamfLogTextView, self).initWithFrame_(frame)
        if self is None:
            return None

        # Set defaults.
        self.setString_(NSString.stringWithString_(text))
        self.setDrawsBackground_(True)
        self.setSelectable_(False)
        self.setFont_(NSFont.userFixedPitchFontOfSize_(12))
        self.setAlignment_(NSLeftTextAlignment)
        self.contentHuggingPriorityForOrientation_(
            NSLayoutConstraintOrientationVertical)

        return self


class JamfLogSource(NSObject):
    # Data source for an NSTableView that displays an array of text lines.
    # Line breaks are assumed to be LF, and partial lines from incremental
    # reading is handled.

    log_file_data = NSMutableArray.alloc().init()
    log_file_color = NSMutableArray.alloc().init()
    last_line_is_partial = False

    def addLine_partial_(self, line, isPartial):
        if self.last_line_is_partial:
            new_line, color = self.parseLineAttr_(
                self.log_file_data.lastObject() + line)
            self.log_file_data.removeLastObject()
            self.log_file_color.removeLastObject()
            self.log_file_data.addObject_(new_line)
            self.log_file_color.addObject_(color)
        else:
            new_line, color = self.parseLineAttr_(line)
            self.log_file_data.addObject_(new_line)
            self.log_file_color.addObject_(color)
        self.last_line_is_partial = isPartial

    def nsColorForColor_(self, color):
        if color == u"black":
            return NSColor.blackColor()
        elif color == u"blue":
            return NSColor.blueColor()
        elif color == u"brown":
            return NSColor.brownColor()
        elif color == u"cyan":
            return NSColor.cyanColor()
        elif color == u"darkgray":
            return NSColor.darkGrayColor()
        elif color == u"gray":
            return NSColor.grayColor()
        elif color == u"green":
            return NSColor.greenColor()
        elif color == u"lightgray":
            return NSColor.lightGrayColor()
        elif color == u"magenta":
            return NSColor.magentaColor()
        elif color == u"orange":
            return NSColor.orangeColor()
        elif color == u"purple":
            return NSColor.purpleColor()
        elif color == u"red":
            return NSColor.redColor()
        elif color == u"white":
            return NSColor.lightGrayColor()
            #return NSColor.whiteColor()
        elif color == u"yellow":
            return NSColor.yellowColor()
        else:
            return NSColor.blackColor()

    def parseLineAttr_(self, line):
        if line.startswith(u"%{") and u"}" in line:
            attrStr, _, rest = line[2:].partition(u"}")
            NSLog(u"attrStr = %@", repr(attrStr))
            color = NSColor.blackColor()
            for attr in [x.strip() for x in attrStr.split(u",")]:
                NSLog(u"attr = %@", repr(attr))
                if u"=" in attr:
                    key, value = [x.strip().lower() for x in attr.split(u"=", 1)]
                    NSLog(u"key = %@, value = %@", repr(key), repr(value))
                    if key == u"color":
                        color = self.nsColorForColor_(value)
                    else:
                        NSLog(u"Unknown attribute key: %@", repr(key))
                else:
                    NSLog(u"Unknown attribute: %@", repr(attr))
            return rest, color
        else:
            return line, NSColor.blackColor()

    def removeAllLines(self):
        self.log_file_data.removeAllObjects()

    def lineCount(self):
        return self.log_file_data.count()

    def numberOfRowsInTableView_(self, tableView):
        return self.lineCount()

    def tableView_objectValueForTableColumn_row_(self, tableView, column, row):
        return self.log_file_data.objectAtIndex_(row)

    def tableView_dataCellForTableColumn_row_(self, tableView, column, row):
        if column:
            cell = column.dataCell()
            cell.setTextColor_(self.log_file_color[row])
            cell.setFont_(NSFont.userFixedPitchFontOfSize_(12))
            return cell
        else:
            return None


class JamfLogWindow(NSWindowController):
    # Initialize class instance variables.
    backdrop_window = NSWindow.alloc()
    computer_name_data = NSString.alloc().init()
    computer_name_label = JamfLogTextField.alloc()
    computer_name = JamfLogTextField.alloc()
    jamf_command_scroll = JamfLogScrollView.alloc()
    jamf_command_label = JamfLogTextField.alloc()
    jamf_command = JamfLogTextView.alloc().init()
    network_scroll = JamfLogScrollView.alloc()
    network_label = JamfLogTextField.alloc()
    network = JamfLogTextView.alloc().init()
    log_file_data = JamfLogSource.alloc().init()
    log_view_scroll = JamfLogScrollView.alloc()
    log_view = JamfLogTable.alloc().init()
    quit_app = JamfLogButton.alloc()
    refresh_view = JamfLogButton.alloc()
    window = NSWindow.alloc()
    file_handle = None
    update_timer = None

    def showLogWindow_(self, title):
        self.log_view.setDelegate_(self.log_file_data)
        self.key_window = Cocoa.NSApp().keyWindow()

        # Base all sizes on the screen's dimensions.
        screen_rectangle = NSScreen.mainScreen().frame()

        # Resize the log window so that it leaves a border on all sides.
        # Add a little extra border at the bottom so we don't cover the
        # loginwindow message.
        window_rectangle = screen_rectangle.copy()
        window_rectangle.origin.x = 0
        window_rectangle.origin.y = 0
        window_rectangle.size.width -= 200.0
        window_rectangle.size.height -= 300.0

        # Open a log window that covers most of the screen. Since we are
        # bypassing InterfaceBuilder, we will need to initialize and configure
        # each interface element programmatically.
        self.window.initWithContentRect_styleMask_backing_defer_(
            window_rectangle, 15, 2, 0)
        self.window.setDelegate_(self)
        self.window.setTitle_(title)
        # This is the key piece that allows this to run at login.
        self.window.setCanBecomeVisibleWithoutLogin_(True)
        self.window.setLevel_(NSScreenSaverWindowLevel - 1)
        self.window.center()
        self.window.orderFrontRegardless()

        # Create a rectangle smaller than the window's rectangle that we will
        # then use to define both the NSScrollView and nested NSTableView.
        text_rectangle = window_rectangle.copy()
        text_rectangle.origin.x = 10.0
        text_rectangle.origin.y = 80.00
        text_rectangle.size.width -= 20.0
        text_rectangle.size.height -= 90.0

        # Add the log_view NSTableView object. This is where the log will
        # appear
        self.window.contentView().addSubview_(self.log_view)

        # Add a column to the log_view NSTableView as it defaults to having
        # no columns.
        self.column_identifier = NSString.stringWithString_(u"Column0")
        self.table_column = NSTableColumn.alloc().initWithIdentifier_(
            self.column_identifier)
        self.table_column.setWidth_(text_rectangle.size.width)
        self.log_view.addTableColumn_(self.table_column)

        # Initialize the NSScrollView object that will contain the NSTableView
        self.log_view_scroll.initWithFrame_(text_rectangle)
        self.window.contentView().addSubview_(self.log_view_scroll)
        # Put the NSTableView into the NSScrollView
        self.log_view_scroll.setDocumentView_(self.log_view)

        # Create buttons.
        self.refresh_view.initWithOptions(
            title="Refresh", position=(10.0, 40.0), key_equivalent="\\r",
            target=self.key_window, action=self.refreshLog)
        self.window.contentView().addSubview_(self.refresh_view)
        self.window.setDefaultButtonCell_(self.refresh_view)

        self.quit_app.initWithOptions(
            title="Quit", position=(10.0, 10.0),
            target=self.key_window, action='terminate:')
        self.window.contentView().addSubview_(self.quit_app)

        # Create computer name labels.
        self.computer_name_label.initWithOptions(
            NSString.stringWithString_(u"Computer Name:"),
            ((200.0, 45.0), (200.0, 20.0)))
        self.window.contentView().addSubview_(self.computer_name_label)

        self.computer_name.initWithOptions(
            NSString.stringWithString_(u"Unkown"),
            ((200.0, 15.0), (200.0, 30.0)))
        self.computer_name.setFont_(NSFont.boldSystemFontOfSize_(18))
        self.window.contentView().addSubview_(self.computer_name)

        self.jamf_command_frame = (
            (520.0, 10.0),
            (((text_rectangle.size.width - 555) / 2) - 100, 60.0))

        # Create Jamf command fields. These will show a listing of commands
        # currently being executed by the jamf framework.
        self.jamf_command_label.initWithOptions(
            NSString.stringWithString_(u"Jamf Processes:"),
            ((410.0, 15.0), (100.0, 50.0)))
        self.jamf_command_label.setFont_(NSFont.systemFontOfSize_(16))
        self.jamf_command_label.setAlignment_(NSRightTextAlignment)
        self.window.contentView().addSubview_(self.jamf_command_label)

        self.jamf_command.initWithOptions(
            NSString.stringWithString_(u"Unknown"), self.jamf_command_frame)
        self.window.contentView().addSubview_(self.jamf_command)

        # Put the NSTextView into the NSScrollView
        # Initialize the NSScrollView object that will contain the list of
        # jamf commands currently being executed.
        self.jamf_command_scroll.initWithFrame_(self.jamf_command_frame)
        self.window.contentView().addSubview_(self.jamf_command_scroll)
        self.jamf_command_scroll.setDocumentView_(self.jamf_command)

        self.network_frame = self.jamf_command.frame().copy()

        # Create network fields. These will show a listing of currently
        # connected network devices.
        self.network_label.initWithOptions(
            NSString.stringWithString_(u"Network Connections:"),
            ((self.network_frame.origin.x +
              self.network_frame.size.width + 10, 15.0), (100.0, 50.0)))
        self.network_label.setFont_(NSFont.systemFontOfSize_(16))
        self.network_label.setAlignment_(NSRightTextAlignment)
        self.window.contentView().addSubview_(self.network_label)

        self.network_frame.origin.x = (self.network_frame.origin.x +
                                       self.network_frame.size.width + 110)
        self.network_frame.size.width = (text_rectangle.size.width -
                                         self.network_frame.origin.x)

        self.network.initWithOptions(
            NSString.stringWithString_(u"Unknown"), self.network_frame)
        self.window.contentView().addSubview_(self.network)

        # Put the NSTextView into the NSScrollView
        self.network_scroll.initWithFrame_(self.network_frame)
        self.window.contentView().addSubview_(self.network_scroll)
        self.network_scroll.setDocumentView_(self.network)

        # Create a transparent, black backdrop window that covers the whole
        # screen and fade it in slowly.
        self.backdrop_window.initWithContentRect_styleMask_backing_defer_(
            screen_rectangle, 0, 2, 0)
        self.backdrop_window.setCanBecomeVisibleWithoutLogin_(True)
        self.backdrop_window.setLevel_(NSStatusWindowLevel)
        self.backdrop_window.setFrame_display_(screen_rectangle, True)
        translucent_color = NSColor.blackColor().colorWithAlphaComponent_(0.75)
        self.backdrop_window.setBackgroundColor_(translucent_color)
        self.backdrop_window.setOpaque_(False)
        self.backdrop_window.setIgnoresMouseEvents_(False)
        self.backdrop_window.setAlphaValue_(0.0)
        self.backdrop_window.orderFrontRegardless()
        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(1.0)
        self.backdrop_window.animator().setAlphaValue_(1.0)
        NSAnimationContext.endGrouping()

    def watchLogFile_(self, logFile):
        # Display and continuously update a log file in the main window.
        self.stopWatching()
        self.log_file_data.removeAllLines()
        self.log_view.setDataSource_(self.log_file_data)
        self.log_view.reloadData()
        self.file_handle = NSFileHandle.fileHandleForReadingAtPath_(logFile)
        self.refreshLog()
        # Kick off a timer that updates the log view periodically.
        self.update_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            5.00,
            self,
            u"refreshLog",
            None,
            True
        )

    def stopWatching(self):
        # Release the file handle and stop the update timer.
        if self.file_handle is not None:
            self.file_handle.closeFile()
            self.file_handle = None
        if self.update_timer is not None:
            self.update_timer.invalidate()
            self.update_timer = None

    def refreshLog(self):
        # Check for new available data, read it, and scroll to the bottom.
        data = self.file_handle.availableData()
        if data.length():
            utf8string = NSString.alloc().initWithData_encoding_(
                data,
                NSUTF8StringEncoding
            )
            for line in utf8string.splitlines(True):
                if line.endswith(u"\\n"):
                    self.log_file_data.addLine_partial_(
                        line.rstrip(u"\\n"), False)
                else:
                    self.log_file_data.addLine_partial_(line, True)
            self.log_view.reloadData()
            self.log_view.scrollRowToVisible_(
                self.log_file_data.lineCount() - 1)
        self.computer_name.setStringValue_(self.get_sc_computername())
        self.computer_name.displayIfNeeded()
        self.jamf_command.setString_(self.get_jamf_command())
        self.jamf_command.scrollToBeginningOfDocument_(self.jamf_command)
        self.jamf_command.displayIfNeeded()
        self.network.setString_(self.get_network_info())
        self.network.scrollToBeginningOfDocument_(self.network)
        self.network.displayIfNeeded()

    def get_sc_computername(self):
        # Gets the computer name from SystemConfiguration
        try:
            return SCPreferencesGetValue(
                SCPreferencesCreate(None, "SystemConfiguration", None),
                "System")["System"]["ComputerName"]
        except:
            # Return False for any exception.
            return NSString.stringWithString_("Unknown")

    def get_network_info(self):
        # Gets network information from SystemConfiguration
        try:
            # Have to use capWords because underscores break here.
            connectedDevices = list()
            query = SCDynamicStoreCreate(
                None, u"FindCurrentInterfaceIpMac", None, None)
            interfaces = SCDynamicStoreCopyValue(
                query, u"State:/Network/Interface").get("Interfaces")
            for interface in interfaces:
                status = SCDynamicStoreCopyValue(
                    query, u"State:/Network/Interface/" +
                    interface + "/IPv4")
                if status is not None and interface != "lo0":
                    connectedDevices.append(
                        dict(interface=interface,
                             address=status.get("Addresses")))
            # Weak references break this. So I have to associate this method
            # with a Python object.
            copiedInterfaces = SCNetworkInterfaceCopyAll()
            for interface in copiedInterfaces:
                bsdName = SCNetworkInterfaceGetBSDName(interface)
                try:
                    [i.update(
                        name=SCNetworkInterfaceGetLocalizedDisplayName(interface),
                        mac=SCNetworkInterfaceGetHardwareAddressString(interface))
                     for i in connectedDevices if i["interface"] == bsdName]
                except TypeError:
                    pass

            return NSString.stringWithString_(
                "\\n".join(
                    ["%s\\t%s\\t%s (%s)" %
                     (i["mac"], i["address"][0], i["name"], i["interface"])
                     for i in connectedDevices]))

        except KeyError:
            # Don't want a blanket exception.
            return NSString.stringWithString_("Unknown")

    def get_jamf_command(self):
        # Gets the computer name from SystemConfiguration
        try:
            return NSString.stringWithString_(
                subprocess.check_output(
                    ["pgrep", "-fl", "jamf"]))
        except:
            # Return False for any exception.
            return NSString.stringWithString_("Unknown")

    def windowWillClose_(self, notification):
        # If main window is closed with close button, close the backdrop
        # window. This is the "last" window, and therefore the AppDelegate
        # will close the application.
        self.backdrop_window.close()


class AppDelegate(NSObject):
    log_window_controller = JamfLogWindow.alloc().init()
    prefs = NSUserDefaults.standardUserDefaults()

    def applicationDidFinishLaunching_(self, aNotification):
        self.prefs.registerDefaults_({
            u"logfile": u"/var/log/jamf.log",
        })
        logfile = self.prefs.stringForKey_(u"logfile")
        self.log_window_controller.showLogWindow_(logfile)
        self.log_window_controller.watchLogFile_(logfile)

    def applicationShouldTerminateAfterLastWindowClosed_(self, aNotification):
        return True


def main():
    # Main application thread
    # Remove menu by making the app a UI element. This allows the clock to be
    # viewed while running.
    info = NSBundle.mainBundle().infoDictionary()
    info['LSUIElement'] = True
    app = NSApplication.sharedApplication()

    # NSApp.setDelegate_() doesn't retain a reference to the delegate object,
    # and will get picked up by garbage collection. By assigning the
    # AppDelegate object to a local variable, the reference is maintained.
    delegate = AppDelegate.alloc().init()
    NSApp().setDelegate_(delegate)

    app.activateIgnoringOtherApps_(True)

    AppHelper.runEventLoop()


if __name__ == '__main__':
    main()

""")

# If script already exists, then check its contents against the script above.
if os.path.exists(log_script_file):
    with open(log_script_file, 'r') as fp:
        existing_script = fp.read()
    print("Script exists. Checking its contents against master script.")
else:
    # We need to set existing_script to something, so we will set it to None
    # so that it does not match below.
    existing_script = None
    print("Script does not exist. Will create.")

# If the script doesn't match or doesn't exist, then we will write it anew.
if existing_script != log_script:
    # Since this will be running early in the DEP imaging process, we will
    # most likely need to make the directory.
    if not os.path.exists(os.path.dirname(log_script_file)):
        os.makedirs(os.path.dirname(log_script_file), 0o700)
    # Write the above script to a file.
    with open(log_script_file, "w") as file:
        file.write(log_script)

    #-----------------------
    # fix permissions on script
    #-----------------------

    os.lchown(log_script_file, uid, gid)
    os.chmod(launch_agent_file, 0o755)

    print("New script file written.")

else:
    print("Script file matches master. No need to update. Exiting.")

# Start the LaunchAgent:
# Created the launchctl commands in a list.
launchctl_list = [
    [LAUNCHCTL, "bootstrap", "loginwindow", launch_agent_file],
    [LAUNCHCTL, "enable", "loginwindow/" + launch_agent_label],
    [LAUNCHCTL, "kickstart", "-k", "loginwindow/" + launch_agent_label]]

# Run the launchctl commands, but don't pipe their output as that will create
# a lot of noise in the logs.
for cmd in launchctl_list:
    try:
        subprocess.check_call(cmd)
        print(" ".join(cmd) + " - succeeded.")
    except subprocess.CalledProcessError:
        print(" ".join(cmd) + " - did not succeed.")

sys.exit(0)
