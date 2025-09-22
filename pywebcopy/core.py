# Copyright 2020; Raja Tomar
# See license for more details
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional
from functools import cached_property

from .elements import WebElement
from .schedulers import crawler_scheduler
from .schedulers import default_scheduler
from .schedulers import threading_crawler_scheduler
from .schedulers import threading_default_scheduler

__all__ = ['WebPage', 'Crawler']

logger = logging.getLogger(__name__)


class WebPage(WebElement):
    """
    WebPage built upon HTMLResource element.
    It provides various utilities like form-filling,
    external response processing, getting list of links,
    dumping html and opening the html in the browser.
    """

    __slots__ = ()  # no extra per-instance dict; attrs live in WebElement

    @classmethod
    def from_config(cls, config) -> "WebPage":
        """Create a WebPage from a configured config object."""
        if config and not config.is_set():
            raise AttributeError("Configuration is not setup.")

        # Localize lookups once
        threaded = config.get('threaded')
        if threaded:
            scheduler = threading_default_scheduler(timeout=config.get_thread_join_timeout())
        else:
            scheduler = default_scheduler()

        session = config.create_session()
        context = config.create_context()
        # NOTE: __init__ implemented in WebElement; cls(session, config, scheduler, context)
        return cls(session, config, scheduler, context)

    @cached_property
    def element_map(self):
        """Registry of different handler for different tags.

        Cached once per instance; avoids repeated attribute traversal on scheduler.
        """
        return self.scheduler.data

    def save_complete(self, pop: bool = False) -> str:
        """Save complete html+assets to disk and optionally open in a browser."""
        # Bind to locals to reduce attribute lookups in tight call paths.
        scheduler = self.scheduler
        scheduler.handle_resource(self)
        if pop:
            self.open_in_browser()
        return self.filepath

    def open_in_browser(self) -> bool:
        """Open the page in the default browser if it has been saved."""
        fp = self.filepath
        if not fp or not os.path.isabs(fp):
            # Fallback to original guard; avoid resolving partial paths
            if not fp or not os.path.exists(fp):
                self.logger.info("Can't find the file to open in browser: %s", fp)
                return False

        if not Path(fp).is_file():
            self.logger.info("Can't find the file to open in browser: %s", fp)
            return False

        self.logger.info("Opening default browser with file: %s", fp)
        import webbrowser  # lazy import preserves startup perf
        return webbrowser.open('file:///' + fp)

    # handy shortcuts
    run = crawl = save_assets = save_complete


class Crawler(WebPage):
    __slots__ = ()

    @classmethod
    def from_config(cls, config) -> "Crawler":
        """Create a Crawler (site-wide) from a configured config object."""
        if config and not config.is_set():
            raise AttributeError("Configuration is not setup.")

        threaded = config.get('threaded')
        if threaded:
            scheduler = threading_crawler_scheduler(timeout=config.get_thread_join_timeout())
        else:
            scheduler = crawler_scheduler()

        session = config.create_session()
        context = config.create_context()
        return cls(session, config, scheduler, context)
