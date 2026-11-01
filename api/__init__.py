"""
api/ - the web server between the React screens (web/) and the brain (core/).

The React app runs in the browser, so it can't import core/ the way the
notebook does. This server wraps every core/ function the screens need in a
web address like /api/risks, and hands back plain JSON.
"""
