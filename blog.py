#!/usr/bin/env python
#
# Copyright 2009 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import functools
import markdown
import os.path
import re
import tornado.web
import tornado.wsgi
import unicodedata
import wsgiref.handlers

from google.appengine.api import users
from google.appengine.ext import db


class Snippet(db.Model):
    """A single snippet."""
    title = db.StringProperty(required=True)
    raw_content = db.TextProperty(required=True)
    tags = db.StringListProperty()
    category = db.StringListProperty()
    author = db.UserProperty()
    language = db.StringProperty(required=True)
    published = db.DateTimeProperty(auto_now_add=True)
    updated = db.DateTimeProperty(auto_now=True)

def administrator(method):
    """Decorate with this method to restrict to site admins."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        if not self.current_user:
            if self.request.method == "GET":
                self.redirect(self.get_login_url())
                return
            raise tornado.web.HTTPError(403)
        elif not self.current_user.administrator:
            if self.request.method == "GET":
                self.redirect("/")
                return
            raise tornado.web.HTTPError(403)
        else:
            return method(self, *args, **kwargs)
    return wrapper


class BaseHandler(tornado.web.RequestHandler):
    """Implements Google Accounts authentication methods."""
    def get_current_user(self):
        user = users.get_current_user()
        if user: user.administrator = users.is_current_user_admin()
        return user

    def get_login_url(self):
        return users.create_login_url(self.request.uri)

    def render_string(self, template_name, **kwargs):
        # Let the templates access the users module to generate login URLs
        return tornado.web.RequestHandler.render_string(
            self, template_name, users=users, **kwargs)


class HomeHandler(BaseHandler):
    def get(self):
        snippets = db.Query(Snippet).order('-published').fetch(limit=5)
        if not snippets:
            if not self.current_user or self.current_user.administrator:
                self.redirect("/compose")
                return
        snippet = Snippet(language='Python', raw_content='asd', title='asd')
        self.render("home.html", snippets=snippets, snippet=snippet)

class SnippetHandler(BaseHandler):
    def get(self, slug):
        snippet = db.Query(Snippet).filter("slug =", slug).get()
        if not snippet: raise tornado.web.HTTPError(404)
        self.render("snippet.html", entry=entry)


class ArchiveHandler(BaseHandler):
    def get(self):
        entries = db.Query(Snippet).order('-published')
        self.render("archive.html", entries=entries)


class FeedHandler(BaseHandler):
    def get(self):
        entries = db.Query(Snippet).order('-published').fetch(limit=10)
        self.set_header("Content-Type", "application/atom+xml")
        self.render("feed.xml", entries=entries)


class ComposeHandler(BaseHandler):
    @administrator
    def get(self):
        key = self.get_argument("key", None)
        snippet = Snippet.get(key) if key else None
        self.render("compose.html", snippet=snippet)

    @administrator
    def post(self):
        key = self.get_argument("key", None)
        if key:
            snippet = Snippet.get(key)
            snippet.title = self.get_argument("title")
            snippet.markdown = self.get_argument("markdown")
            snippet.html = markdown.markdown(self.get_argument("markdown"))
        else:
            title = self.get_argument("title")
            slug = unicodedata.normalize("NFKD", title).encode(
                "ascii", "ignore")
            slug = re.sub(r"[^\w]+", " ", slug)
            slug = "-".join(slug.lower().strip().split())
            if not slug: slug = "snippet"
            while True:
                existing = db.Query(Snippet).filter("slug =", slug).get()
                if not existing or str(existing.key()) == key:
                    break
                slug += "-2"
            snippet = Snippet(
                author=self.current_user,
                title=title,
                slug=slug,
                markdown=self.get_argument("markdown"),
                html=markdown.markdown(self.get_argument("markdown")),
            )
        snippet.put()
        self.redirect("/snippet/" + snippet.slug)


class SnippetModule(tornado.web.UIModule):
    def render(self, snippet):
        return self.render_string("modules/snippet.html", entry=entry)


settings = {
    "blog_title": u"PySnippets",
    "template_path": os.path.join(os.path.dirname(__file__), "templates"),
    "ui_modules": {"Snippet": SnippetModule},
    "xsrf_cookies": True,
}
application = tornado.wsgi.WSGIApplication([
    (r"/", HomeHandler),
    (r"/archive", ArchiveHandler),
    (r"/feed", FeedHandler),
    (r"/snippet/([^/]+)", SnippetHandler),
    (r"/compose", ComposeHandler),
], **settings)


def main():
    wsgiref.handlers.CGIHandler().run(application)


if __name__ == "__main__":
    main()
