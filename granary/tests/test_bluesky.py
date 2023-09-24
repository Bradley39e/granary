"""Unit tests for bluesky.py.

Most tests are via files in testdata/.
"""
import copy
from unittest.mock import patch

from oauth_dropins.webutil import testutil, util
from oauth_dropins.webutil.testutil import NOW, requests_response
import requests

from ..bluesky import (
  as1_to_profile,
  at_uri_to_web_url,
  blob_to_url,
  Bluesky,
  did_web_to_url,
  from_as1,
  to_as1,
  url_to_did_web,
  web_url_to_at_uri,
)
from ..source import ALL, FRIENDS, ME, SELF

ACTOR_AS = {
  'objectType' : 'person',
  'id': 'did:web:alice.com',
  'displayName': 'Alice',
  'image': [{'url': 'https://alice.com/alice.jpg'}],
  'url': 'https://alice.com/',
}
ACTOR_PROFILE_VIEW_BSKY = {
  '$type': 'app.bsky.actor.defs#profileView',
  'did': 'did:web:alice.com',
  'handle': 'alice.com',
  'displayName': 'Alice',
  'avatar': 'https://alice.com/alice.jpg',
  'description': None,
}
NEW_BLOB = {  # new blob format: https://atproto.com/specs/data-model#blob-type
  '$type': 'blob',
  'ref': {'$link': 'bafkreim'},
  'mimeType': 'image/jpeg',
  'size': 154296,
}
NEW_BLOB_URL = 'https://bsky.social/xrpc/com.atproto.sync.getBlob?did=did:plc:foo&cid=bafkreim'
OLD_BLOB = {  # old blob format: https://atproto.com/specs/data-model#blob-type
  'cid': 'bafyjrot',
  'mimeType': 'image/jpeg',
}
OLD_BLOB_URL = 'https://bsky.social/xrpc/com.atproto.sync.getBlob?did=did:plc:foo&cid=bafyjrot'
ACTOR_PROFILE_BSKY = {
  '$type': 'app.bsky.actor.profile',
  'displayName': 'Alice',
  'avatar': NEW_BLOB,
  'banner': OLD_BLOB,
  'description': None,
}

POST_AS = {
  'objectType': 'activity',
  'verb': 'post',
  'object': {
    'objectType': 'note',
    'id': 'at://did/app.bsky.feed.post/tid',
    'url': 'https://bsky.app/profile/did/post/tid',
    'published': '2007-07-07T03:04:05',
    'content': 'My original post',
  }
}
POST_HTML = """
<article class="h-entry">
  <main class="e-content">My original post</main>
  <a class="u-url" href="http://orig/post"></a>
  <time class="dt-published" datetime="2007-07-07T03:04:05"></time>
</article>
"""
POST_BSKY = {
  '$type': 'app.bsky.feed.defs#feedViewPost',
  'post': {
    '$type': 'app.bsky.feed.defs#postView',
    'uri': 'at://did/app.bsky.feed.post/tid',
    'cid': 'TODO',
    'record': {
      '$type': 'app.bsky.feed.post',
      'text': 'My original post',
      'createdAt': '2007-07-07T03:04:05',
    },
    'replyCount': 0,
    'repostCount': 0,
    'upvoteCount': 0,
    'downvoteCount': 0,
    'indexedAt': '2022-01-02T03:04:05+00:00',
  }
}
POST_AUTHOR_AS = copy.deepcopy(POST_AS)
POST_AUTHOR_AS['object'].update({
  'author': ACTOR_AS,
  'url': 'https://bsky.app/profile/alice.com/post/tid',
})
POST_AUTHOR_PROFILE_AS = copy.deepcopy(POST_AUTHOR_AS)
POST_AUTHOR_PROFILE_AS['object']['author'].update({
  'username': 'alice.com',
  'url': 'https://bsky.app/profile/alice.com',
})
POST_AUTHOR_BSKY = copy.deepcopy(POST_BSKY)
POST_AUTHOR_BSKY['post']['author'] = {
  **ACTOR_PROFILE_VIEW_BSKY,
  '$type': 'app.bsky.actor.defs#profileViewBasic',
}

FACETS = [{
  '$type': 'app.bsky.richtext.facet',
  'features': [{
    '$type': 'app.bsky.richtext.facet#link',
    'uri': 'http://my/link',
  }],
  'index' : {
    'byteStart' : 3,
    'byteEnd' : 11,
  },
}]
FACET_TAG = {
  'objectType': 'article',
  'url': 'http://my/link',
  'displayName': 'original',
  'startIndex': 3,
  'length': 8,
}
EMBED_EXTERNAL = {
  'description': '',
  'title': 'a link',
  'uri': 'http://my/link',
}
EMBED_EXTERNAL_ATTACHMENT = {
  'objectType': 'link',
  'url': 'http://my/link',
  'displayName': 'a link',
}
POST_AS_EMBED = {
  **POST_AS['object'],
  'attachments': [EMBED_EXTERNAL_ATTACHMENT],
}
POST_BSKY_EMBED = copy.deepcopy(POST_BSKY)
POST_BSKY_EMBED['post']['record']['embed'] = {
  '$type': 'app.bsky.embed.external',
  'external': {
    '$type': 'app.bsky.embed.external#external',
    **EMBED_EXTERNAL,
  },
}
POST_BSKY_EMBED['post']['embed'] = {
  '$type': 'app.bsky.embed.external#view',
  'external': {
    '$type': 'app.bsky.embed.external#viewExternal',
    **EMBED_EXTERNAL,
  },
}
POST_AS_IMAGES = copy.deepcopy(POST_AS)
POST_AS_IMAGES['object']['image'] = [{
  'url': 'http://my/pic',
  'displayName': 'my alt text',
}]
POST_BSKY_IMAGES = copy.deepcopy(POST_BSKY)
POST_BSKY_IMAGES['post']['embed'] = {
  '$type': 'app.bsky.embed.images#view',
  'images': [{
    '$type': 'app.bsky.embed.images#viewImage',
    'alt': 'my alt text',
    'fullsize': 'http://my/pic',
    'thumb': 'http://my/pic',
  }],
}
POST_BSKY_IMAGES['post']['record']['embed'] = {
  '$type': 'app.bsky.embed.images',
  'images': [{
    '$type': 'app.bsky.embed.images#image',
    'alt': 'my alt text',
    'image': 'TODO',
  }],
}

REPLY_AS = {
  'objectType': 'activity',
  'verb': 'post',
  'object': {
    'objectType': 'comment',
    'published': '2008-08-08T03:04:05',
    'content': 'I hereby reply to this',
    'id': 'at://did/app.bsky.feed.post/tid',
    'url': 'https://bsky.app/profile/did/post/tid',
    'inReplyTo': [{
      'id': 'at://did/app.bsky.feed.post/parent-tid',
      'url': 'https://bsky.app/profile/did/post/parent-tid',
    }],
  },
}
REPLY_HTML = """
<article class="h-entry">
  <main class="e-content">I hereby reply to this</a></main>
  <a class="u-in-reply-to" href="http://orig/post"></a>
  <a class="u-url" href="http://a/reply"></a>
  <time class="dt-published" datetime="2008-08-08T03:04:05"></time>
</article>
"""
REPLY_BSKY = copy.deepcopy(POST_BSKY)
REPLY_BSKY['post'].update({
  'uri': 'at://did/app.bsky.feed.post/tid',
  'record': {
    '$type': 'app.bsky.feed.post',
    'text': 'I hereby reply to this',
    'createdAt': '2008-08-08T03:04:05',
    'reply': {
      '$type': 'app.bsky.feed.post#replyRef',
      'root': {
        '$type': 'com.atproto.repo.strongRef',
        'uri': '',
        'cid': 'TODO',
      },
      'parent': {
        '$type': 'com.atproto.repo.strongRef',
        'uri': 'at://did/app.bsky.feed.post/parent-tid',
        'cid': 'TODO',
      },
    },
  },
})

REPOST_AS = {
  'objectType': 'activity',
  'verb': 'share',
  'actor': {
    'objectType' : 'person',
    'id': 'did:web:bob.com',
    'displayName': 'Bob',
    'url': 'https://bsky.app/profile/bob.com',
  },
  'object': POST_AUTHOR_PROFILE_AS['object'],
}
REPOST_BSKY = copy.deepcopy(POST_AUTHOR_BSKY)
REPOST_BSKY['reason'] = {
  '$type': 'app.bsky.feed.defs#reasonRepost',
  'by': {
    '$type': 'app.bsky.actor.defs#profileViewBasic',
    'did': 'did:web:bob.com',
    'handle': 'bob.com',
    'displayName': 'Bob',
  },
  'indexedAt': NOW.isoformat(),
}

THREAD_AS = copy.deepcopy(POST_AS)
THREAD_AS['object']['replies'] = [REPLY_AS['object']]
THREAD_BSKY = {
  '$type' : 'app.bsky.feed.defs#threadViewPost',
  'post' : POST_AUTHOR_BSKY['post'],
  'replies': [REPLY_BSKY['post']],
}

class BlueskyTest(testutil.TestCase):

  def setUp(self):
    self.bs = Bluesky('handull', access_token='towkin')
    util.now = lambda **kwargs: testutil.NOW

  def assert_equals(self, expected, actual, ignore=(), **kwargs):
    ignore = list(ignore) + ['uri']
    return super().assert_equals(expected, actual, ignore=ignore, **kwargs)

  def test_url_to_did_web(self):
    for bad in None, '', 'foo', 'did:web:bar.com':
      with self.assertRaises(ValueError):
        url_to_did_web(bad)

    self.assertEqual('did:web:foo.com', url_to_did_web('https://foo.com'))
    self.assertEqual('did:web:foo.com', url_to_did_web('https://foo.com/'))
    self.assertEqual('did:web:foo.com', url_to_did_web('https://foo.com:3000'))
    self.assertEqual('did:web:foo.bar.com', url_to_did_web('https://foo.bar.com/baz/baj'))

  def test_did_web_to_url(self):
    for bad in None, '', 'foo' 'https://bar.com', 'did:web:foo.com:path':
      with self.assertRaises(ValueError):
        did_web_to_url(bad)

    self.assertEqual('https://foo.com/', did_web_to_url('did:web:foo.com'))
    self.assertEqual('https://foo.bar.com/', did_web_to_url('did:web:foo.bar.com'))

  def test_user_url(self):
    self.assertEqual('https://bsky.app/profile/snarfed.org',
                     Bluesky.user_url('snarfed.org'))

    self.assertEqual('https://bsky.app/profile/snarfed.org',
                     Bluesky.user_url('@snarfed.org'))

  def test_post_url(self):
    self.assertEqual('https://bsky.app/profile/snarfed.org/post/3jv3wdw2hkt25',
                     Bluesky.post_url('snarfed.org', '3jv3wdw2hkt25'))

  def test_at_uri_to_web_url(self):
    self.assertEqual(None, at_uri_to_web_url(''))

    at_uri = 'at://did:plc:asdf/app.bsky.feed.post/3jv3wdw2hkt25'
    self.assertEqual(
      'https://bsky.app/profile/did:plc:asdf/post/3jv3wdw2hkt25',
      at_uri_to_web_url(at_uri))
    self.assertEqual(
      'https://bsky.app/profile/snarfed.org/post/3jv3wdw2hkt25',
      at_uri_to_web_url(at_uri, handle='snarfed.org'))

    with self.assertRaises(ValueError):
      at_uri_to_web_url('http://not/at/uri')

  def test_web_url_to_at_uri(self):
    for url, expected in (
        ('', None),
        ('https://bsky.app/profile/foo.com', 'at://foo.com'),
        ('https://bsky.app/profile/did:plc:foo', 'at://did:plc:foo'),
        ('https://bsky.app/profile/did:plc:foo/post/3jv3wdw2hkt25',
         'at://did:plc:foo/app.bsky.feed.post/3jv3wdw2hkt25'),
        ('https://bsky.app/profile/bsky.app/feed/mutuals',
         'at://bsky.app/app.bsky.feed.generator/mutuals'),
    ):
      self.assertEqual(expected, web_url_to_at_uri(url))

    for url in ('at://foo', 'http://not/bsky.app', 'https://bsky.app/x'):
      with self.assertRaises(ValueError):
        web_url_to_at_uri(url)

  def test_from_as1_post(self):
    self.assert_equals(POST_BSKY, from_as1(POST_AS), ignore=['uri'])

  def test_from_as1_post_with_author(self):
    self.assert_equals(POST_AUTHOR_BSKY, from_as1(POST_AUTHOR_AS))

  def test_from_as1_post_html_with_tag_indices_not_implemented(self):
    post_as = copy.deepcopy(POST_AS)
    post_as['object'].update({
      'content': '<em>some html</em>',
      'content_is_html': True,
      'tags': [FACET_TAG],
    })

    with self.assertRaises(NotImplementedError):
      from_as1(post_as)

  def test_from_as1_post_without_tag_indices(self):
    post_as = copy.deepcopy(POST_AS)
    post_as['object']['tags'] = [{
      'url': 'http://my/link',
    }]

    expected = copy.deepcopy(POST_BSKY)
    expected['post']['record']['facets'] = copy.deepcopy(FACETS)
    del expected['post']['record']['facets'][0]['index']
    self.assert_equals(expected, from_as1(post_as))

  def test_from_as1_post_with_image(self):
    self.assert_equals(POST_BSKY_IMAGES, from_as1(POST_AS_IMAGES))

  def test_from_as1_object_vs_activity(self):
    obj = {
      'objectType': 'note',
      'content': 'foo',
    }
    activity = {
      'verb': 'post',
      'object': obj,
    }
    self.assert_equals(from_as1(obj), from_as1(activity))

  def test_from_as1_actor_handle(self):
    for expected, fields in (
        ('', {}),
        ('fooey.bsky.social', {'username': 'fooey.bsky.social'}),
        ('fooey.com', {'username': 'fooey.com', 'url': 'http://my/url', 'id': 'tag:nope'}),
        ('foo.com', {'url': 'http://foo.com'}),
        ('foo.com', {'url': 'http://foo.com/path'}),
    ):
      self.assert_equals(expected, from_as1({
        'objectType' : 'person',
        **fields,
      })['handle'])

  def test_from_as1_actor_id_not_url(self):
    """Tests error handling when attempting to generate did:web."""
    self.assertEqual('did:web:foo.com', from_as1({
      'objectType' : 'person',
      'id': 'tag:foo.com,2001:bar',
    })['did'])

  def test_from_as1_composite_url(self):
    self.assertEqual({
      '$type': 'app.bsky.actor.defs#profileView',
      'did': 'did:web:rodentdisco.co.uk',
      'handle': 'rodentdisco.co.uk',
      'description': None,
    }, from_as1({
      'objectType' : 'person',
      'url': {
        "displayName": "my web site",
        "value": "https://rodentdisco.co.uk/author/dan/"
      },
    }))

  def test_from_as1_embed(self):
    self.assert_equals(POST_BSKY_EMBED, from_as1(POST_AS_EMBED))

  def test_from_as1_facet_link_and_embed(self):
    expected = copy.deepcopy(POST_BSKY_EMBED)
    expected['post']['record']['facets'] = FACETS

    self.assert_equals(expected, from_as1({
      **POST_AS_EMBED,
      'tags': [FACET_TAG],
    }))

  def test_from_as1_follow_no_actor(self):
    with self.assertRaises(ValueError):
      from_as1({
        'objectType' : 'activity',
        'verb': 'follow',
        'object': 'at://did:plc:foo/com.atproto.actor.profile/123',
      })

  def test_from_as1_follow_no_object(self):
    with self.assertRaises(ValueError):
      from_as1({
        'objectType' : 'activity',
        'verb': 'follow',
        'actor': 'at://did:plc:foo/com.atproto.actor.profile/123',
      })

  def test_as1_to_profile(self):
    self.assert_equals({
      '$type': 'app.bsky.actor.profile',
      'description': None,
      'displayName': 'Alice',
    }, as1_to_profile(ACTOR_AS))

  def test_as1_to_profile_not_actor(self):
    with self.assertRaises(ValueError):
      as1_to_profile(POST_AS)

  def test_to_as1_profile(self):
    self.assert_equals({
      'objectType': 'person',
      'id': 'did:plc:foo',
      'displayName': 'Alice',
      'username': 'han.dull',
      'image': [{
        'url': NEW_BLOB_URL,
      }, {
        'objectType': 'featured',
        'url': OLD_BLOB_URL,
      }],
    }, to_as1(ACTOR_PROFILE_BSKY, repo_did='did:plc:foo', repo_handle='han.dull'))

  def test_to_as1_profile_no_repo_did_handle_or_pds(self):
    self.assert_equals({
      'objectType': 'person',
      'displayName': 'Alice',
    }, to_as1(ACTOR_PROFILE_BSKY, repo_did=None, pds='http://foo'))
    self.assert_equals({
      'objectType': 'person',
      'id': 'did:plc:foo',
      'displayName': 'Alice',
    }, to_as1(ACTOR_PROFILE_BSKY, repo_did='did:plc:foo', pds=None))

  def test_to_as1_post(self):
    self.assert_equals(POST_AS['object'], to_as1(POST_BSKY))

  def test_to_as1_post_with_author(self):
    self.assert_equals(POST_AUTHOR_PROFILE_AS['object'], to_as1(POST_AUTHOR_BSKY))

  def test_to_as1_post_type_kwarg(self):
    post_bsky = copy.deepcopy(POST_AUTHOR_BSKY)
    type = post_bsky.pop('$type')
    del post_bsky['post']['$type']
    del post_bsky['post']['author']['$type']
    self.assert_equals(POST_AUTHOR_PROFILE_AS['object'], to_as1(post_bsky, type=type))

  def test_to_as1_post_with_image(self):
    self.assert_equals(POST_AS_IMAGES['object'], to_as1(POST_BSKY_IMAGES))

  def test_to_as1_missing_objectType(self):
    with self.assertRaises(ValueError):
      to_as1({'foo': 'bar'})

  def test_to_as1_unknown_objectType(self):
    with self.assertRaises(ValueError):
      to_as1({'objectType': 'poll'})

  def test_to_as1_missing_type(self):
    with self.assertRaises(ValueError):
      to_as1({'foo': 'bar'})

  def test_to_as1_unknown_type(self):
    with self.assertRaises(ValueError):
      to_as1({'$type': 'app.bsky.foo'})

  def test_to_as1_embed(self):
    self.assert_equals(POST_AS_EMBED, to_as1(POST_BSKY_EMBED))

  def test_to_as1_embed_block(self):
    self.assertIsNone(to_as1({
      '$type': 'app.bsky.embed.record#viewBlocked',
      'uri': 'unused',
    }))

  def test_to_as1_facet_link_and_embed(self):
    bsky = copy.deepcopy(POST_BSKY_EMBED)
    bsky['post']['record']['facets'] = FACETS

    expected = {
      **POST_AS_EMBED,
      'tags': [FACET_TAG],
    }
    self.assert_equals(expected, to_as1(bsky))

  def test_blob_to_url(self):
    self.assertIsNone(blob_to_url(blob={'foo': 'bar'}, repo_did='x', pds='y'))
    self.assertEqual(NEW_BLOB_URL, blob_to_url(blob=NEW_BLOB,
                                               repo_did='did:plc:foo'))
    self.assertEqual(OLD_BLOB_URL, blob_to_url(blob=OLD_BLOB,
                                               repo_did='did:plc:foo'))

  def test_constructor_both_access_token_and_app_password_error(self):
    with self.assertRaises(AssertionError):
      Bluesky('handull', access_token='towkin', app_password='pazzwurd')

  def test_constructor_access_token(self):
    bs = Bluesky('handull', access_token='towkin')
    self.assertEqual('towkin', bs.access_token)

  @patch('requests.post')
  def test_constructor_app_password(self, mock_post):
    mock_post.return_value = requests_response({
      'handle': 'real.han.dull',
      'did': 'did:plc:me',
      'accessJwt': 'towkin',
    })

    bs = Bluesky('handull', app_password='pazzwurd')
    self.assertEqual('real.han.dull', bs.handle)
    self.assertEqual('did:plc:me', bs.did)
    self.assertEqual('towkin', bs.access_token)

    mock_post.assert_called_once_with(
        'https://bsky.social/xrpc/com.atproto.server.createSession',
        json={'identifier': 'handull', 'password': 'pazzwurd'},
        headers={
          'Content-Type': 'application/json',
          'User-Agent': util.user_agent,
        },
    )

  @patch('requests.get')
  def test_get_activities_friends(self, mock_get):
    mock_get.return_value = requests_response({
      'cursor': 'timestamp::cid',
      'feed': [POST_AUTHOR_BSKY, REPOST_BSKY],
    })

    expected_repost = copy.deepcopy(REPOST_AS)
    expected_repost['actor']['username'] = 'bob.com'
    self.assert_equals([POST_AUTHOR_PROFILE_AS['object'], expected_repost],
                       self.bs.get_activities(group_id=FRIENDS))

    mock_get.assert_called_once_with(
        'https://bsky.social/xrpc/app.bsky.feed.getTimeline',
        json=None,
        headers={
          'Authorization': 'Bearer towkin',
          'Content-Type': 'application/json',
          'User-Agent': util.user_agent,
        },
    )

  @patch('requests.get')
  def test_get_activities_activity_id(self, mock_get):
    mock_get.return_value = requests_response({
      '$type' : 'app.bsky.feed.defs#threadViewPost',
      'thread': THREAD_BSKY,
      'replies': [REPLY_BSKY],
    })

    self.assert_equals([POST_AUTHOR_PROFILE_AS['object']],
                       self.bs.get_activities(activity_id='at://id'))
    mock_get.assert_called_once_with(
        'https://bsky.social/xrpc/app.bsky.feed.getPostThread?uri=at%3A%2F%2Fid&depth=1',
        json=None,
        headers={
          'Authorization': 'Bearer towkin',
          'Content-Type': 'application/json',
          'User-Agent': util.user_agent,
        },
    )

  def test_get_activities_bad_activity_id(self):
    with self.assertRaises(ValueError):
      self.bs.get_activities(activity_id='not_at_uri')

  @patch('requests.get')
  def test_get_activities_self_user_id(self, mock_get):
    mock_get.return_value = requests_response({
      'cursor': 'timestamp::cid',
      'feed': [POST_AUTHOR_BSKY],
    })

    self.assert_equals([POST_AUTHOR_PROFILE_AS['object']],
                       self.bs.get_activities(group_id=SELF, user_id='alice.com'))
    mock_get.assert_called_once_with(
        'https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed?actor=alice.com',
        json=None,
        headers={
          'Authorization': 'Bearer towkin',
          'Content-Type': 'application/json',
          'User-Agent': util.user_agent,
        },
    )
