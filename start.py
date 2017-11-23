#!/usr/bin/python3

"""
This is a technology demonstrator for the depeche protocol, it is not
meant for use in a hostile environment, as it makes no special
provisions for destroying password buffers or... anything really.

Please note that running this in a generic context reuires a number of dependencies:

* sqlite
* pynacl

And possibly others - Just can't think of what they might be right now.
"""

import os
import logging
import argparse
import configparser

import depeche.ui.curses as curses

DEFAULT_CONFIG_FILE_NAME = os.path.expanduser("~") + "/.depeche/depeche.config"

def main(args):
    """
    Main entry point to the depeche tech demo CLI - If no arguments are given,
    the default curses interfce will be started.
    """
    conf = configparser.ConfigParser()
    conf.read(args.config_file)

    try:
        log_file_path = conf.get("logging", "log_file")
    except (configparser.NoSectionError, configparser.NoOptionError):
        logging.info("No configuration found for log file. Using default.")
        log_file_path = "ddep.log"
    logging.basicConfig(filename=log_file_path, level=args.log_level)

    curses.CursesInterface.main_screen_turn_on(conf)

def get_args():
    parser = argparse.ArgumentParser(
        prog="ddep",
        description="The demonstrator program for the Depeche protocol.")

    parser.add_argument(
        "-c", "--config_file",
        default=DEFAULT_CONFIG_FILE_NAME,
        help="Configuration file for ddep if not located in the standard location",
        metavar="filepath",
        type=str)

    parser.add_argument(
        "--log_level",
        default=logging.ERROR,
        help="You may select log level to display if something is not working.")

    args = parser.parse_args()
    return args

if __name__ == "__main__":
    args = get_args()
    main(args)
