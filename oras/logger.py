__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2022, Vanessa Sochat"
__license__ = "Apache-2.0"

import logging as _logging
import platform
import sys
import os
import threading
from typing import Union, TextIO, Text
from pathlib import Path
import inspect


class ColorizingStreamHandler(_logging.StreamHandler):
    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)
    RESET_SEQ = "\033[0m"
    COLOR_SEQ = "\033[%dm"
    BOLD_SEQ = "\033[1m"

    colors = {
        "WARNING": YELLOW,
        "INFO": GREEN,
        "DEBUG": BLUE,
        "CRITICAL": RED,
        "ERROR": RED,
    }

    def __init__(
        self,
        nocolor: bool = False,
        stream: Union[Text, Path, TextIO] = sys.stderr,
        use_threads: bool = False,
    ):
        """
        Create a new ColorizingStreamHandler

        Arguments
        ---------
        nocolor     : do not use color
        stream      : stream list to this output
        use_threads : use threads! lol
        """
        super().__init__(stream=stream)
        self._output_lock = threading.Lock()
        self.nocolor = nocolor or not self.can_color_tty()

    def can_color_tty(self) -> bool:
        """
        Determine if the tty supports color
        """
        if "TERM" in os.environ and os.environ["TERM"] == "dumb":
            return False
        return self.is_tty and not platform.system() == "Windows"

    @property
    def is_tty(self) -> bool:
        """
        Determine if we have a tty environment
        """
        isatty = getattr(self.stream, "isatty", None)
        return isatty and isatty()

    def emit(self, record):
        """
        Emit a log record

        Arguments
        ---------
        record : the record to emit
        """
        with self._output_lock:
            try:
                self.format(record)  # add the message to the record
                self.stream.write(self.decorate(record))
                self.stream.write(getattr(self, "terminator", "\n"))
                self.flush()
            except BrokenPipeError as e:
                raise e
            except (KeyboardInterrupt, SystemExit):
                # ignore any exceptions in these cases as any relevant messages have been printed before
                pass
            except Exception:
                self.handleError(record)

    def decorate(self, record) -> str:
        """
        Decorate a log record

        Arguments
        ---------
        record : the record to decorate
        """
        message = record.message
        message = [message]
        if not self.nocolor and record.levelname in self.colors:
            message.insert(0, self.COLOR_SEQ % (30 + self.colors[record.levelname]))
            message.append(self.RESET_SEQ)
        return "".join(message)


class Logger:
    def __init__(self):
        """
        Create a new logger
        """
        self.logger = _logging.getLogger(__name__)
        self.log_handler = [self.text_handler]
        self.stream_handler = None
        self.printshellcmds = False
        self.quiet = False
        self.logfile = None
        self.last_msg_was_job_info = False
        self.logfile_handler = None

    def cleanup(self):
        """
        Close open files, etc. for the logger
        """
        if self.logfile_handler is not None:
            self.logger.removeHandler(self.logfile_handler)
            self.logfile_handler.close()
        self.log_handler = [self.text_handler]

    def handler(self, msg: str):
        """
        Handle a log message.

        Arguments
        ---------
        msg : the message to handle
        """
        for handler in self.log_handler:
            handler(msg)

    def set_stream_handler(self, stream_handler):
        """
        Set a stream handler.

        Arguments
        ---------
        stream_handler : the stream handler
        """
        if self.stream_handler is not None:
            self.logger.removeHandler(self.stream_handler)
        self.stream_handler = stream_handler
        self.logger.addHandler(stream_handler)

    def set_level(self, level):
        """
        Set the logging level.

        Arguments
        ---------
        level : the logging level to set
        """
        self.logger.setLevel(level)

    def location(self, msg: str):
        """
        Debug level message with location info.

        Arguments
        ---------
        msg : the logging message
        """
        callerframerecord = inspect.stack()[1]
        frame = callerframerecord[0]
        info = inspect.getframeinfo(frame)
        self.debug(
            "{}: {info.filename}, {info.function}, {info.lineno}".format(msg, info=info)
        )

    def info(self, msg: str):
        """
        Info level message

        Arguments
        ---------
        msg : the informational message
        """
        self.handler(dict(level="info", msg=msg))

    def warning(self, msg: str):
        """
        Warning level message

        Arguments
        ---------
        msg : the warning message
        """
        self.handler({"level": "warning", "msg": msg})

    def debug(self, msg: str):
        """
        Debug level message

        Arguments
        ---------
        msg : the debug message
        """
        self.handler({"level": "debug", "msg": msg})

    def error(self, msg: str):
        """
        Error level message

        Arguments
        ---------
        msg : the error message
        """
        self.handler({"level": "error", "msg": msg})

    def exit(self, msg: str, return_code: int = 1):
        """
        Error level message and exit with error code

        Arguments
        ---------
        msg : the informational message
        """
        self.handler({"level": "error", "msg": msg})
        sys.exit(return_code)

    def progress(self, done: int = None, total: int = None):
        """
        Show piece of a progress bar

        Arguments
        ---------
        done : count of total that is complete
        total : count of total
        """
        self.handler({"level": "progress", "done": done, "total": total})

    def shellcmd(self, msg: str):
        """
        Shellcmd message

        Arguments
        ---------
        msg : the error message
        """
        if msg is not None:
            msg = {"level": "shellcmd", "msg": msg}
            self.handler(msg)

    def text_handler(self, msg: dict):
        """
        The default log handler that prints to the console.

        Arguments
        ---------
        msg : the log message dictionary
        """
        level = msg["level"]
        if level == "info" and not self.quiet:
            self.logger.info(msg["msg"])
        if level == "warning":
            self.logger.warning(msg["msg"])
        elif level == "error":
            self.logger.error(msg["msg"])
        elif level == "debug":
            self.logger.debug(msg["msg"])
        elif level == "progress" and not self.quiet:
            done = msg["done"]
            total = msg["total"]
            p = done / total
            percent_fmt = ("{:.2%}" if p < 0.01 else "{:.0%}").format(p)
            self.logger.info(
                "{} of {} steps ({}) done".format(done, total, percent_fmt)
            )
        elif level == "shellcmd":
            if self.printshellcmds:
                self.logger.warning(msg["msg"])


logger = Logger()


def setup_logger(
    quiet: bool = False,
    printshellcmds: bool = False,
    nocolor: bool = False,
    stdout: bool = False,
    debug: bool = False,
    verbose: bool = False,
    use_threads: bool = False,
):
    """
    Setup the logger. This should be called from an init or client.

    Arguments
    ---------
    quiet          : set logging level to quiet
    printshellcmds : a special level to print shell commands
    nocolor        : do not use color
    stdout         : standard output for the logger
    debug          : debug level logging
    verbose        : verbose level logging
    use_threads    : use threads!
    """
    # console output only if no custom logger was specified
    stream_handler = ColorizingStreamHandler(
        nocolor=nocolor,
        stream=sys.stdout if stdout else sys.stderr,
        use_threads=use_threads,
    )
    level = _logging.INFO
    if verbose:
        level = _logging.VERBOSE
    elif debug:
        level = _logging.DEBUG

    logger.set_stream_handler(stream_handler)
    logger.set_level(level)
    logger.quiet = quiet
    logger.printshellcmds = printshellcmds
