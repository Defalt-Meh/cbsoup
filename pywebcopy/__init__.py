import logging
import warnings

__version__ = "0.0.0+local"

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = ['save_website', 'save_webpage']


def save_page(url,
              project_folder=None,
              project_name=None,
              bypass_robots=None,
              debug=False,
              open_in_browser=True,
              delay=None,
              threaded=None,):
    """Easiest way to save any single webpage with images, css and js.

    example::

        from pywebcopy import save_webpage
        save_webpage(
            url="https://httpbin.org/",
            project_folder="E://savedpages//",
            project_name="my_site",
            bypass_robots=True,
            debug=True,
            open_in_browser=True,
            delay=None,
            threaded=False,
        )

    :param url: url of the web page to work with
    :type url: str
    :param project_folder: folder in which the files will be downloaded
    :type project_folder: str
    :param project_name: name of the project to distinguish it
    :type project_name: str | None
    :param bypass_robots: whether to follow the robots.txt rules or not
    :param debug: whether to print deep logs or not.
    :param open_in_browser: whether to open a new tab after saving the webpage.
    :type open_in_browser: bool
    :param delay: amount of delay between two concurrent requests to a same server.
    :param threaded: whether to use threading or not (it can break some site).
    """
    from .configs import get_config
    config = get_config(url, project_folder, project_name, bypass_robots, debug, delay, threaded)
    page = config.create_page()
    page.get(url)
    if threaded:
        warnings.warn(
            "Opening in browser is not supported when threading is enabled!")
        open_in_browser = False
    page.save_complete(pop=open_in_browser)


save_web_page = save_webpage = save_page


def save_website(url,
                 project_folder=None,
                 project_name=None,
                 bypass_robots=None,
                 debug=False,
                 open_in_browser=False,
                 delay=None,
                 threaded=None):
    """Crawls the entire website for html, images, css and js.

    example::

        from pywebcopy import save_website
        save_website(
            url="https://httpbin.org/",
            project_folder="E://savedpages//",
            project_name="my_site",
            bypass_robots=True,
            debug=False,
            open_in_browser=True,
            delay=None,
            threaded=False,
        )

    :param url: url of the web page to work with
    :type url: str
    :param project_folder: folder in which the files will be downloaded
    :type project_folder: str
    :param project_name: name of the project to distinguish it
    :type project_name: str | None
    :param bypass_robots: whether to follow the robots.txt rules or not
    :param debug: whether to print deep logs or not.
    :param open_in_browser: whether to open a new tab after saving the webpage.
    :type open_in_browser: bool
    :param delay: amount of delay between two concurrent requests to a same server.
    :param threaded: whether to use threading or not (it can break some site).
    """
    from .configs import get_config
    config = get_config(url, project_folder, project_name, bypass_robots, debug, delay, threaded)
    crawler = config.create_crawler()
    crawler.get(url)
    if threaded:
        warnings.warn(
            "Opening in browser is not supported when threading is enabled!")
        open_in_browser = False
    crawler.save_complete(pop=open_in_browser)