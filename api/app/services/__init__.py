"""Services: the work the routers delegate to.

A router's job is HTTP — read the request, check who is asking, call something,
shape the response. Anything that talks to a model lives here instead, so the
prompts have one home and can be tested without a web request.
"""
