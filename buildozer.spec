[app]

# (str) Title of your application
title = CampoData
source.dir = .
# (str) Package name
package.name = campodata

# (str) Package domain (needed for android packaging)
package.domain = com.maldonado.agro

# (list) Source files to include (let it blank to include all files)
source.include_exts = py,png,jpg,kv,atlas

# (list) List of inclusion patterns relative to the root directory
source.include_patterns = assets/*,*.jpg,*.png

# (list) Source files to exclude (let it blank to not exclude anything)
source.exclude_exts = spec

# (list) List of directory to exclude (relative to source.dir)
source.exclude_dirs = tests, bin, venv

# (list) List of exclusions in source files
source.exclude_patterns = license,images/bad/*

# (str) Application versioning
version = 1.0.1

# (list) Application requirements
requirements = python3,kivy,requests,pillow,pyjnius,certifi,urllib3,idna,charset-normalizer,sqlite3

# (list) Custom source folders for dependencies
#source.custom_path =

# (str) Icon of the application
icon.filename = %(source.dir)s/logo.png

# (str) Supported orientations (landscape, sensor, portrait or all)
orientation = portrait

# (list) List of services to declare
#services = 

#
# OSX Specific
#

#
# Android specific
#

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Permissions
android.permissions = INTERNET,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,CAMERA,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE

# (list) Features
android.features = android.hardware.camera,android.hardware.location.gps

# (int) Target Android API, should be as high as possible.
android.api = 35

# (int) Minimum API your APK will support.
android.minapi = 21

# (str) Android NDK version to use
android.ndk = 25b

# (str) Android SDK version to use
#android.sdk = 20

# (str) android add library (./libs folder)
#android.add_libs_implementation = 

# (list) The android archs to build for, in order of decreasing priority.
android.archs = arm64-v8a, armeabi-v7a

# (bool) If True, then p4a will perform a clean build
android.clear_cache = False

# -------------------------------------------------------------------------
# CONFIGURACIÓN DE FIRMA DIGITAL (KEYSTORE)
# -------------------------------------------------------------------------
android.keystore = maldonado.keystore
android.keyalias = key_maldonado
android.keystore_password = maldonado2026
android.keyalias_password = maldonado2026

#
# Python for android (p4a) specific
#

# (str) python-for-android branch to use
p4a.branch = master

[buildozer]

# (int) Log level (0 = error, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = Zaps, 1 = correct keycodes)
warn_root = 1
p4a.branch = master