__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import inspect
import logging as _logging
import os
import platform
import sys
import threading
from pathlib import Path
from typing import Optional, Text, TextIO, Union


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

        :param nocolor: do not use color
        :type nocolor: bool
        :param stream: stream list to this output
        :type stream: bool
        :param use_threads: use threads! lol
        :type use_threads: bool
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
        return isatty and isatty()  # type: ignore

    def emit(self, record: _logging.LogRecord):
        """
        Emit a log record

        :param record: the record to emit
        :type record: logging.LogRecord
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

        :param record: the record to emit
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

    def handler(self, msg: dict):
        """
        Handle a log message.

        :param msg: the message to handle
        :type msg: dict
        """
        for handler in self.log_handler:
            handler(msg)

    def set_stream_handler(self, stream_handler: _logging.Handler):
        """
        Set a stream handler.

        :param stream_handler : the stream handler
        :type stream_handler: logging.Handler
        """
        if self.stream_handler is not None:
            self.logger.removeHandler(self.stream_handler)
        self.stream_handler = stream_handler
        self.logger.addHandler(stream_handler)

    def set_level(self, level: int):
        """
        Set the logging level.

        :param level: the logging level to set
        :type level: int
        """
        self.logger.setLevel(level)

    def location(self, msg: str):
        """
        Debug level message with location info.

        :param msg: the logging message
        :type msg: dict
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

        :param msg: the informational message
        :type msg: str
        """
        self.handler({"level": "info", "msg": msg})

    def warning(self, msg: str):
        """
        Warning level message

        :param msg: the warning message
        :type msg: str
        """
        self.handler({"level": "warning", "msg": msg})

    def debug(self, msg: str):
        """
        Debug level message

        :param msg: the debug message
        :type msg: str
        """
        self.handler({"level": "debug", "msg": msg})

    def error(self, msg: str):
        """
        Error level message

        :param msg: the error message
        :type msg: str
        """
        self.handler({"level": "error", "msg": msg})

    def exit(self, msg: str, return_code: int = 1):
        """
        Error level message and exit with error code

        :param msg: the exiting (error) message
        :type msg: str
        :param return_code: return code to exit on
        :type return_code: int
        """
        self.handler({"level": "error", "msg": msg})
        sys.exit(return_code)

    def progress(self, done: int = None, total: int = None):
        """
        Show piece of a progress bar

        :param done: count of total that is complete
        :type done: int
        :param total: count of total
        :type total: int
        """
        self.handler({"level": "progress", "done": done, "total": total})

    def shellcmd(self, msg: Optional[str]):
        """
        Shellcmd message

        :param msg: the message
        :type msg: str
        """
        if msg is not None:
            self.handler({"level": "shellcmd", "msg": msg})

    def text_handler(self, msg: dict):
        """
        The default log handler that prints to the console.

        :param msg: the log message dict
        :type msg: dict
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
    use_threads: bool = False,
):
    """
    Setup the logger. This should be called from an init or client.

    :param quiet: set logging level to quiet
    :type quiet: bool
    :param printshellcmds: a special level to print shell commands
    :type printshellcmds: bool
    :param nocolor: do not use color
    :type nocolor: bool
    :param stdout: print to standard output for the logger
    :type stdout: bool
    :param debug: debug level logging
    :type debug: bool
    :param use_threads: use threads!
    :type use_threads: bool
    """
    # console output only if no custom logger was specified
    stream_handler = ColorizingStreamHandler(
        nocolor=nocolor,
        stream=sys.stdout if stdout else sys.stderr,
        use_threads=use_threads,
    )
    level = _logging.INFO
    if debug:
        level = _logging.DEBUG

    logger.set_stream_handler(stream_handler)
    logger.set_level(level)
    logger.quiet = quiet
    logger.printshellcmds = printshellcmds
