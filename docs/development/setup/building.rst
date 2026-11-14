=============================
Building Blender from Source
=============================
.. _development-setup-buildblender:

As a developer, there are a number of advantages that come from building from source:
* Avoid having to wait for bug fixes from full releases
* Building the latest version to test compatibility early
* Testing new features and how we can integrate with them
* Blender can be built as a python module, which can improve IDE integration.

The Blender code repo is also managed by git, allowing ease of integration into our workflow. There are some
additional prerequisite utilities that need to be installed first.

See - https://wiki.blender.org/wiki/Building_Blender

.. _development-setup-buildplugin:

The repo comes with scripts which will package up the addon for use

===================================
Building the Blender Niftools Addon
===================================

The Blender Niftools Addon is a python project which can be manually put into the Blender extensions directory. The
repo provides a build script which creates a zip file that can be installed through the Blender preferences menu.

.. note::
    Ensure that you have installed Git and Python 3.11 or newer. Source dependencies will be fetched automatically

---------
Build Zip
---------

To build the addon from a git checkout, run the following:

.. code-block:: shell

    python install/build.py

The zip file is written to ``install/temp/``.

-------
Install
-------

Set ``BLENDER_EXTENSIONS_DIR`` to Blender's ``user_default`` extensions repository, for example
``%APPDATA%\Blender Foundation\Blender\5.3\extensions\user_default`` (Windows) or
``~/.config/blender/5.3/extensions/user_default`` (Linux), then run:

.. code-block:: shell

    python install/build.py --install

-------
Options
-------

``--extensions-dir DIR``
    Install location (overriding ``BLENDER_EXTENSIONS_DIR``).
``--generated-dir DIR``
    Skip codegen and use an existing cobra-tools ``generated`` folder.
``--keep-temp``
    Keep the codegen and nifgen folders in ``install/temp`` for debugging.
``--clean-cache``
    Delete ``install/.cache`` and fetch the pinned sources again.
