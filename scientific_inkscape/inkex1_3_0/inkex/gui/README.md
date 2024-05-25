# What is inkex.gui

This module is a Gtk based GUI creator. It helps extensions launch their own user interfaces and can help make sure those interfaces will work on all platforms that Inkscape ships with.

# How do I use it

You can create custom user interfaces by using the [Gnome Glade builder program](https://gitlab.gnome.org/GNOME/glade). Once you have a layout of all the widgets you want, you then make a GtkApp and Window classes inside your Python program, when the GtkApp is run, the windows will be shown to the user and all signals specified for the widgets will call functions on your window class.

Please see the existing code for examples of how to do this.

# This is a fork

This code was originally part of the package `gtkme` which contained some parts we didn't want to ship&mdash;such as Ubuntu indicators and internet pixmaps. To avoid conflicts, our stripped down version of the `gtkme` module is renamed and placed inside of Inkscape's `inkex` module.
