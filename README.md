# Automatic File Transfer

A small Windows desktop application that watches a source folder and
automatically copies newly added or changed files to a destination folder.
The destination can be a local folder or a network share. Subfolder structure is preserved.

## Why this project exists

This project started as a way to transfer Assetto Corsa telemetry files
between two PCs on the same network. One PC runs Assetto Corsa, while another
can analyze the data with MoTeC. The transfer is not live: files are copied
when they are created or updated, for example when a driver returns to thepipipipipi
pits.

The tool is not limited to Assetto Corsa or MoTeC. It can be used whenever
you want files added to or changed in one folder to be copied automatically to another folder.

## How it works

- Select a source folder and a destination folder, then enable automatic
  transfer.
- The application watches the source folder and its subfolders for new,
  changed, or moved files.
- Before copying, it waits for a file's size and modification time to stop
  changing, so it does not normally copy a file while it is still being
  written.
- The source folder's subfolder structure is recreated in the destination.
- The application never overwrites an existing destination file. If a
  filename is already taken, it adds a number, such as `session (1).ld`.
- The selected folder paths are saved in the current Windows user's profile.
- The application must remain open while you want it to watch the source folder.

> **This is a one-way automatic copy, not a two-way sync or a full mirror.**
> Files that were already in the source folder when monitoring starts are not
> copied retroactively. Deletions in the source are not propagated to the
> destination. If a source file changes after a copy, the changed version is
> copied as a new file rather than replacing an earlier copy.

## Run the application on Windows

The standalone executable is intended for Windows 64-bit. Copy
`dist\TransfertMotec.exe` to the PC where you want to monitor files and run it.
Python and pip are not required on that PC.

On the first launch, choose the source and destination folders and click the
button to enable automatic transfer. The application currently has a
French-language interface.

The executable is not digitally signed, so Windows SmartScreen may show a warning when you first run it. Only run executables you trust.

## Build the standalone executable

Building requires Python and an internet connection on the development PC; the
PC that runs the finished executable does not need Python.

From PowerShell in the project directory, run:

```powershell
.\build_exe.bat
```

The script installs the packages listed in `requirements-build.txt` and
creates `dist\TransfertMotec.exe` as a single-file, windowed Windows
application. Copy that executable to the target PC. Run the script again after
making changes to build an updated version.

## Run from Python

For development, install Python 3.10 or later. From PowerShell in the project
directory, install the application dependencies and start the app:

```powershell
py -m pip install -r requirements.txt
py .\transfer_app.py
```

Then select the source and destination folders and enable automatic transfer.

## Run the tests

With the development dependencies installed, run:

```powershell
py -m unittest discover -s tests
```

## Network folder notes

- Make sure the Windows account running the application can access and write
  to the destination.
- Test the network path using that same Windows account.
- A UNC path such as `\\server\share\folder` is generally more reliable than a
  mapped network drive, especially when starting the application
  automatically.
- If the network share becomes unavailable, transfer errors are shown in the
  application. Restore access and re-enable monitoring if needed.

## Project dependencies

- Python and Tkinter provide the application and its desktop interface.
- [watchdog](https://python-watchdog.readthedocs.io/) monitors file-system
  events.
- [PyInstaller](https://pyinstaller.org/) packages the app into a standalone
  Windows executable.

Python and PyInstaller are needed to build the executable, but are not
required on the PC that runs it.
