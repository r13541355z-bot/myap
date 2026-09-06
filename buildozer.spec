[app]
title = SearchApp
package.name = searchapp
package.domain = org.example
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1
requirements = python3==3.11.8,kivy,requests,urllib3,certifi,idna,chardet
orientation = portrait
osx.python_version = 3
osx.kivy_version = 1.9.1
fullscreen = 0

[buildozer]
log_level = 2
warn_on_root = 1

android.permissions = INTERNET
android.api = 33
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
