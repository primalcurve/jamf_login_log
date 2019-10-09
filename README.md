# jamf_login_log
Shows the jamf log over the login window.

Based on [LoginLog](https://github.com/MagerValp/LoginLog)

This version does not require packaging an application, as the entire app is contained within the script itself.

The script is merely a wrapper as it writes the script to a directory and then creates a LaunchAgent that executes that script within the `loginwindow` domain. 
