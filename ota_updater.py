# OTA Updater for MicroPython
#
# This module handles checking for and applying updates from a GitHub repository.
# It is designed to be used with a configuration that specifies the repository
# and the files to be updated.

import urequests
import ujson
import os

class OTAUpdater:
    """
    Handles Over-the-Air updates from a GitHub repository.
    """
    def __init__(self, repo_url, files_to_update):
        self.repo_url = repo_url.rstrip('/')
        self.files_to_update = files_to_update
        self.version_file = ".version"
        
        # Construct the API URL from the standard GitHub URL
        parts = self.repo_url.split('/')
        self.api_url = f"https://api.github.com/repos/{parts[-2]}/{parts[-1]}/contents/"
        self.raw_url_base = f"https://raw.githubusercontent.com/{parts[-2]}/{parts[-1]}/main/"

    def _get_remote_version(self):
        """Fetches the latest commit hash from the repository's main branch."""
        try:
            # We check the version of a specific file, e.g., main.py, as a proxy for the repo version
            response = urequests.get(self.api_url + "main.py")
            if response.status_code == 200:
                return response.json()['sha']
            else:
                print(f"Failed to fetch remote version. Status: {response.status_code}")
                return None
        except Exception as e:
            print(f"Error checking remote version: {e}")
            return None

    def _get_local_version(self):
        """Reads the locally stored version (commit hash)."""
        try:
            with open(self.version_file, 'r') as f:
                return f.read().strip()
        except OSError:
            return None # File doesn't exist

    def _save_local_version(self, version):
        """Saves the new version hash locally."""
        with open(self.version_file, 'w') as f:
            f.write(version)

    def check_for_updates(self):
        """Checks if a new version is available."""
        print("Checking for updates...")
        remote_version = self._get_remote_version()
        if not remote_version:
            return False
            
        local_version = self._get_local_version()
        
        print(f"  Remote version: {remote_version}")
        print(f"  Local version:  {local_version}")
        
        if remote_version != local_version:
            print("New version available.")
            return True
        
        print("Device is up to date.")
        return False

    def download_and_install_updates(self):
        """Downloads and replaces specified files from the repository."""
        remote_version = self._get_remote_version()
        if not remote_version:
            print("Cannot download updates, failed to get remote version.")
            return False

        print("Downloading and installing updates...")
        try:
            for filename in self.files_to_update:
                file_url = self.raw_url_base + filename
                print(f"  Downloading {filename} from {file_url}")
                response = urequests.get(file_url)
                
                if response.status_code == 200:
                    with open(filename, 'w') as f:
                        f.write(response.text)
                    print(f"  Successfully updated {filename}")
                else:
                    print(f"  Failed to download {filename}. Status: {response.status_code}")
                    # Optional: Rollback changes here if needed
                    return False
            
            # If all files updated successfully, save the new version
            self._save_local_version(remote_version)
            print("Update process completed successfully.")
            return True

        except Exception as e:
            print(f"An error occurred during the update process: {e}")
            return False
