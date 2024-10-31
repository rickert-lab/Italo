"""
Copyright 2024 The Regents of the University of Colorado

Italo is free software: you can redistribute it and/or modify it under the terms of the
GNU General Public License as published by the Free Software Foundation,
version 3 of the License or any later version.

Italo is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program.
If not, see <https://www.gnu.org/licenses/gpl-3.0>.

Author:     Christian Rickert <christian.rickert@cuanschutz.edu>
Group:      Human Immune Monitoring Shared Resource (HIMSR)
            University of Colorado, Anschutz Medical Campus

Title:      Italo
Summary:    Italo file transfer tool for HALO v0.11 (2024-10-31)
URL:        https://github.com/rickert-lab/Italo

Description:

Italo is used as a file transfer tool for Indica Labs' HALO in the Human Immune Monitoring
Shared Resource (HIMSR) core lab at the University of Colorado | Anschutz Medical Campus.
Search for files in HALO's SQL database and transfer them to a new physical location.
"""

import aiohttp
import asyncio
import json
import os
import platform
import subprocess
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk

import queries


class MainWindow:
    def check_asyncio(self):
        """Helper function for asynchronous calls."""
        self.loop.stop()
        self.loop.run_forever()
        self.root.after(10, self.check_asyncio)

    def copy_file(self, src_path="", dst_path=""):
        """Copy a source file to a destination file.
        Returns the file path of the destination file.
        """
        src_path = os.path.abspath(src_path)
        src_dir, src_file = os.path.split(src_path)
        dst_path = os.path.abspath(dst_path)
        dst_dir, dst_file = os.path.split(dst_path)
        command = {
            "Darwin": ["cp", src_path, os.path.join(dst_dir, src_file)],
            "Linux": ["cp", src_path, os.path.join(dst_dir, src_file)],
            "Windows": [
                "ROBOCOPY",
                src_dir,
                dst_dir,
                src_file,
                "/COMPRESS",
                "/NJH",
                "/NJS",
                "/NP",
            ],
        }.get(platform.system())
        try:
            if platform.system() == "Windows":
                subprocess.run(
                    command, check=False, creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                subprocess.run(command, check=True)
        except subprocess.CalledProcessError as err:
            print(f"Failed to copy file. Error was:\n{err}")
        return os.path.abspath(os.path.join(dst_dir, src_file))

    def on_closing(self):
        """Break the main window loop and exit gracefully."""
        self.loop.stop()
        self.root.destroy()

    def on_search_images(self):
        """Helper function for `search_images`."""
        asyncio.ensure_future(self.search_images(os.path.abspath(self.sentry.get())))

    def on_transfer_images(self):
        """Helper function for `transfer_images`."""
        asyncio.ensure_future(
            self.transfer_images(self.images, os.path.abspath(self.dentry.get()))
        )

    def select_directory(self):
        """Opens a file dialog to select a directory.
        Returns the directory path.
        """
        directory = os.path.abspath(filedialog.askdirectory())
        return directory

    def set_progress_bar(self, value=0):
        """Set the progress bar to a fixed value."""
        self.progress_bar.stop()
        self.progress_bar.config(mode="determinate")
        self.progress_bar["value"] = value

    def set_source(self, directory="", entry=None):
        """Request the source directory from the user and
        write the path string into the sentry widget.
        """
        source_base = self.select_directory()
        self.set_text(self.sentry, source_base)

    def set_target(self, directory="", entry=None):
        """Request the target directory from the user and
        write the path string into the dentry widget.
        """
        target_base = self.select_directory()
        self.set_text(self.dentry, target_base)

    def set_text(self, entry=None, string="", disabled=False):
        """Insert a string into a entry field and
        show the end of the entry's content.
        """
        entry.config(state="normal")  # required for insertion
        entry.delete(0, tk.END)
        entry.insert(0, string)
        entry.xview(tk.END)
        if disabled:
            entry.config(state="disabled")

    def write_secrets(self, file=""):
        """Write a template secrets file."""
        with open(os.path.abspath(file), "w", encoding="utf-8") as secrets_file:
            secrets_template = {
                "client_name": "[GraphQL client name]",
                "client_secret": "[GraphQL client secret]",
                "client_scope": "serviceuser graphql",
                "grant_type": "client_credentials",
                "server_name": "[GraphQL server name]",
            }
            json.dump(secrets_template, secrets_file, indent=2)

    async def get_session(self, secrets_file="secrets.json"):
        """Read GraphQL credentials from a JSON-formatted text file and
        return an authenticated client session with the server.
        """
        session_client = None
        if os.path.isfile(secrets_file):
            secrets = queries.get_secrets(os.path.abspath(secrets_file))
        else:
            self.set_text(self.pentry, "Secrets missing: Template file created.", True)
            self.write_secrets(file=secrets_file)
            if platform.system() == "Windows":  # no support for macOS or Linux
                os.startfile(secrets_file)
            secrets = None
        try:
            credentials = await queries.get_credentials(secrets)
        except aiohttp.client_exceptions.InvalidURL:
            self.set_text(self.pentry, "GraphQL server failed to respond.", True)
        except aiohttp.client_exceptions.ClientConnectionError:
            self.set_text(self.pentry, "GraphQL server failed to connect.", True)
        except aiohttp.client_exceptions.ClientResponseError:
            self.set_text(self.pentry, "GraphQL server reported 'bad request'.", True)
        else:  # success
            session_client = await queries.get_client(secrets, credentials)
        finally:  # failure
            if not session_client:
                self.set_progress_bar()
            return session_client

    async def search_images(self, source_dir=None):
        """Search the HALO GraphQL server for images matching string in their file path.
        Returns a dictionary of matching image IDs with source locations and study names.
        """
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start()
        self.set_text(self.pentry, "Searching...", True)
        session_client = await self.get_session()
        async with session_client as client_session:
            images = await queries.search_images(
                session=client_session, text=source_dir
            )
            matches = {}
            for image_id, image_values in images.items():
                if source_dir == os.path.dirname(image_values["location"]):
                    matches[image_id] = image_values
            studies = set()  # unique studies
            for match in matches.values():
                studies.add(match["studies"])
            self.set_text(
                self.pentry,
                f"FOUND: {len(matches)} image"
                + ("s" if len(matches) != 1 else "")
                + f" in {len(studies)} "
                + ("studies" if len(studies) != 1 else "study")
                + (f" at [{" | ".join(studies)}]." if studies else "."),
                True,
            )
            self.set_progress_bar(value=(100 if len(matches) else 0))
            self.images = matches

    async def transfer_images(self, images=None, target_dir=None):
        """Ask the HALO GraphQL server to change the the source image location
        with the target image location for every image provided.
        Returns a dictionary of image IDs with target locations and transfer errors.
        """
        if not images:
            self.set_text(self.pentry, "No images to transfer.", True)
            return
        if not target_dir.startswith(r"\\"):
            self.set_text(self.pentry, "Target directory must be UNC-style.", True)
            return
        if not os.path.isdir(target_dir):
            self.set_text(self.pentry, "Target directory does not exist.", True)
            return
        self.set_progress_bar()
        self.set_text(self.pentry, "Transfer...", True)
        session_client = await self.get_session()
        async with session_client as client_session:
            transferred = 0
            copied = 0
            for image_id, image_values in images.items():
                source_location = image_values["location"]  # may not exist anymore
                source_name = os.path.basename(source_location)
                target_location = os.path.join(target_dir, source_name)
                self.set_text(self.pentry, f"Tansfer: {source_name}", True)
                if source_location == target_location:
                    self.set_text(
                        self.pentry,
                        "Source and target directories are identical.",
                        True,
                    )
                else:
                    image = await queries.change_location(
                        session=client_session,
                        image_id=image_id,
                        new_location=target_location,
                    )
                    if not image[next(iter(image))]["error"]:
                        transferred += 1
                    if os.path.isfile(source_location) and not os.path.isfile(
                        target_location
                    ):
                        self.set_text(self.pentry, f"Node: {source_name}", True)
                        self.copy_file(source_location, target_location)
                        copied += 1
                    self.set_progress_bar(value=round(transferred / len(images) * 100))
        self.set_text(
            self.pentry,
            f"Nodes: {transferred} image"
            + ("" if len(images) == 1 else "s")
            + ", "
            + f"Files: {copied} image"
            + ("" if len(images) == 1 else "s")
            + ".",
            True,
        )
        self.set_progress_bar(value=(100 if transferred else 0))

    def __init__(self, root):
        # Set up class variable
        self.images = {}

        # Set up root window
        self.root = root
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        root.title("Italo - Image Transfer Tool for HALO v0.1")
        root.minsize(width=600, height=root.winfo_reqheight())

        # Restrict resizing in the Y direction
        root.resizable(True, False)  # Allow resizing in X direction only

        # Configure the root window to expand elements in the X direction
        root.columnconfigure(0, weight=1)

        # Create frames for each row
        self.frame1 = tk.Frame(root)
        self.frame1.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        self.frame2 = tk.Frame(root)
        self.frame2.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        self.frame3 = tk.Frame(root)
        self.frame3.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        self.frame4 = tk.Frame(root)
        self.frame4.grid(row=3, column=0, padx=10, pady=(5, 20))

        # Configure frames to expand elements in the X direction
        self.frame1.columnconfigure(0, weight=1)
        self.frame2.columnconfigure(0, weight=1)
        self.frame3.columnconfigure(0, weight=1)
        self.frame4.columnconfigure(0, weight=1)

        # Create and place the widgets in frame 1
        self.sentry = tk.Entry(self.frame1)
        self.sentry.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=(3, 0))
        self.sentry.insert(0, "[Select source directory]")
        self.sbutton = tk.Button(self.frame1, text="Browse", command=self.set_source)
        self.sbutton.grid(row=0, column=1)

        # Create and place the widgets in frame 2
        self.dentry = tk.Entry(self.frame2)
        self.dentry.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=(3, 0))
        self.dentry.insert(0, "[Select target directory]")
        self.tbutton = tk.Button(self.frame2, text="Browse", command=self.set_target)
        self.tbutton.grid(row=0, column=1)

        # Create and place a separator line in frame 3
        self.separator = ttk.Separator(self.frame3, orient="horizontal")
        self.separator.grid(row=0, column=0, sticky="ew", padx=1, pady=5)

        # Create and place the non-editable text field in frame 3
        self.pentry = tk.Entry(self.frame3)
        self.pentry.grid(row=1, column=0, sticky="ew", padx=0, pady=5)
        self.set_text(
            self.pentry,
            "Copyright 2024 The Regents of the University of Colorado, "
            "HIMSR, Christian Rickert",
            True,
        )

        # Create and place the progress bar in frame 3
        self.progress_bar = ttk.Progressbar(
            self.frame3, orient="horizontal", mode="determinate"
        )
        self.progress_bar.grid(row=2, column=0, sticky="ew", padx=0, pady=0)

        # Create and place the widgets in frame 4
        self.sbutton = tk.Button(
            self.frame4, text="Search", command=self.on_search_images
        )
        self.sbutton.grid(row=0, column=0, padx=5)
        self.tbutton = tk.Button(
            self.frame4, text="Transfer", command=self.on_transfer_images
        )
        self.tbutton.grid(row=0, column=1, padx=5)

        # Center the buttons in frame 4
        self.frame4.grid_columnconfigure(0, weight=1)
        self.frame4.grid_columnconfigure(1, weight=1)
        self.frame4.grid_columnconfigure(2, weight=1)
        self.frame4.grid_columnconfigure(3, weight=1)

        # Manage the asyncio event loop
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.root.after(10, self.check_asyncio)


if __name__ == "__main__":
    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()
