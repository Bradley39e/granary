"""Unit tests for nostr.py."""
from contextlib import contextmanager
from datetime import timedelta
import secrets

from oauth_dropins.webutil.util import json_dumps, json_loads
from oauth_dropins.webutil import testutil

from .. import nostr
from ..nostr import from_as1, id_for, id_to_uri, is_bech32, to_as1, uri_to_id

NOW_TS = int(testutil.NOW.timestamp())
NOW_ISO = testutil.NOW.replace(tzinfo=None).isoformat()
THEN_TS = NOW_TS - 1
THEN_ISO = (testutil.NOW - timedelta(seconds=1)).replace(tzinfo=None).isoformat()

ID = '3bf0c63fcb93463407af97a5e5ee64fa883d107ef9e558472c4eb9aaaefa459d'
URI = 'nostr:npub180cvv07tjdrrgpa0j7j7tmnyl2yr6yr7l8j4s3evf6u64th6gkwsyjh6w6'


NOTE_NOSTR = {
  'kind': 1,
  'id': '12ab',
  'pubkey': '98fe',
  'content': 'Something to say',
}
NOTE_AS1 = {
  'objectType': 'note',
  'id': 'nostr:note1z24swknlsf',
  'author': {'id': 'nostr:npub1nrlqrdny0w'},
  'content': 'Something to say',
}


class FakeConnection:
  """Fake of :class:`websockets.sync.client.ClientConnection`."""
  relay = None
  sent = []
  receive = []

  @classmethod
  def send(cls, msg):
    cls.sent.append(json_loads(msg))

  @classmethod
  def recv(cls):
    return json_dumps(cls.receive.pop())


@contextmanager
def fake_connect(uri):
  """Fake of :func:`websockets.sync.client.connect`."""
  FakeConnection.relay = uri
  yield FakeConnection


class NostrTest(testutil.TestCase):

  def setUp(self):
    super().setUp()

    FakeConnection.relay = None
    FakeConnection.sent = []
    FakeConnection.receive = []

    nostr.connect = fake_connect

  def test_id_for(self):
    self.assertEqual(
      '9adfa2330b391539f46548ff2e088ea964a2f7374898c7335a86e914cbf2e769',
      id_for({
        'pubkey': 'fed987',
        'created_at': NOW_TS,
        'kind': 1,
        'content': 'My plain text',
    }))

  def test_id_to_uri(self):
    self.assertEqual(URI, id_to_uri('npub', ID))

  def test_uri_to_id(self):
    self.assertEqual(ID, uri_to_id(URI))

  def test_is_bech32(self):
    self.assertTrue(is_bech32('nostr:npubabc'))
    self.assertTrue(is_bech32('neventabc'))
    self.assertFalse(is_bech32('abc'))
    self.assertFalse(is_bech32(None))

  def test_to_from_as1_profile(self):
    person = {
      'objectType': 'person',
      'id': 'nostr:npub1z24szqzphd',
      'displayName': 'Alice',
      'description': 'It me',
      'image': 'http://alice/pic',
      'username': 'alice.com',
      'urls': [
        'https://github.com/semisol',
        'https://twitter.com/semisol_public',
        'https://bitcoinhackers.org/@semisol',
        'https://t.me/1087295469',
      ],
    }
    event = {
      'kind': 0,
      'id': '12ab',
      'pubkey': '12ab',
      'content': json_dumps({
        'name': 'Alice',
        'about': 'It me',
        'picture': 'http://alice/pic',
        'nip05': '_@alice.com',
      }, sort_keys=True),
      'tags': [
        ['i', 'github:semisol', '-'],
        ['i', 'twitter:semisol_public', '-'],
        ['i', 'mastodon:bitcoinhackers.org/@semisol', '-'],
        ['i', 'telegram:1087295469', '-'],
      ],
    }
    self.assert_equals(person, to_as1(event))

    # we don't try to detect which URLs might be Mastodon
    del event['tags'][2]
    self.assert_equals(event, from_as1(person))

  def test_to_from_as1_note(self):
    note = {
      'objectType': 'note',
      'id': 'nostr:note1z24swknlsf',
      'author': {'id': 'nostr:npub1nrlqrdny0w'},
      'content': 'Something to say',
      'published': NOW_ISO,
    }
    event = {
      'kind': 1,
      'id': '12ab',
      'pubkey': '98fe',
      'content': 'Something to say',
      'created_at': NOW_TS,
      'tags': [],
    }
    self.assertEqual(note, to_as1(event))
    self.assertEqual(event, from_as1(note))

  def test_to_from_as1_note_subject_tag(self):
    note = {
      'objectType': 'note',
      'id': 'nostr:note1z24swknlsf',
      'content': 'Something to say',
      'title': 'my thing',
    }
    event = {
      'kind': 1,
      'id': '12ab',
      'content': 'Something to say',
      'tags': [
        ['title', 'my thing'],
        ['subject', 'my thing'],
      ],
    }
    self.assertEqual(note, to_as1(event))
    self.assertEqual(event, from_as1(note))

  def test_to_from_as1_note_with_hashtag(self):
    note = {
      'objectType': 'note',
      'id': 'nostr:note1z24swknlsf',
      'author': {'id': 'nostr:npub1nrlqrdny0w'},
      'content': 'Something to say',
      'published': NOW_ISO,
      'tags': [{
        'objectType': 'hashtag',
        'displayName': 'foo',
      }, {
        'objectType': 'hashtag',
        'displayName': 'bar',
      }],
    }
    event = {
      'kind': 1,
      'id': '12ab',
      'pubkey': '98fe',
      'content': 'Something to say',
      'created_at': NOW_TS,
      'tags': [
        ['t', 'foo'],
        ['t', 'bar'],
      ],
    }
    self.assertEqual(note, to_as1(event))
    self.assertEqual(event, from_as1(note))

  def test_to_from_as1_note_with_location(self):
    note = {
      'objectType': 'note',
      'id': 'nostr:note1z24swknlsf',
      'author': {'id': 'nostr:npub1nrlqrdny0w'},
      'content': 'Something to say',
      'published': NOW_ISO,
      'location': {
        'displayName': 'my house',
      },
    }
    event = {
      'kind': 1,
      'id': '12ab',
      'pubkey': '98fe',
      'content': 'Something to say',
      'created_at': NOW_TS,
      'tags': [
        ['location', 'my house'],
      ],
    }
    self.assertEqual(note, to_as1(event))
    self.assertEqual(event, from_as1(note))

  def test_to_from_as1_article(self):
    note = {
      'objectType': 'article',
      'id': 'nostr:note1z24swknlsf',
      'author': {'id': 'nostr:npub1nrlqrdny0w'},
      'title': 'a thing',
      'summary': 'about the thing',
      'content': 'Something to say',
      'published': NOW_ISO,
    }
    event = {
      'kind': 30023,
      'id': '12ab',
      'pubkey': '98fe',
      'content': 'Something to say',
      'created_at': NOW_TS,
      'tags': [
        # TODO: NIP-33 'd' tag for slug
        ['published_at', str(NOW_TS)],
        ['title', 'a thing'],
        ['subject', 'a thing'],
        ['summary', 'about the thing'],
      ],
    }
    self.assertEqual(note, to_as1(event))
    self.assertEqual(event, from_as1(note))

  def test_to_from_as1_reply(self):
    reply = {
      'objectType': 'note',
      'id': 'nostr:note1z24swknlsf',
      'author': {'id': 'nostr:npub1nrlqrdny0w'},
      'published': NOW_ISO,
      'content': 'I hereby reply',
      'inReplyTo': 'nostr:nevent1xnxsm5fasn',
    }
    event = {
      'kind': 1,
      'id': '12ab',
      'pubkey': '98fe',
      'content': 'I hereby reply',
      'tags': [
        ['e', '34cd', 'TODO relay', 'reply'],
      ],
      'created_at': NOW_TS,
    }

    self.assertEqual(reply, to_as1(event))
    self.assertEqual(event, from_as1(reply))

  def test_to_from_as1_repost(self):
    repost = {
      'objectType': 'activity',
      'verb': 'share',
      'id': 'nostr:nevent1z24spd6d40',
      'published': NOW_ISO,
      'object': {
        'objectType': 'note',
        'id': 'nostr:note1xnxs50q044',
        'author': {'id': 'nostr:npub1nrlqrdny0w'},
        'content': 'The orig post',
        'published': THEN_ISO,
      },
    }
    event = {
      'kind': 6,
      'id': '12ab',
      'content': json_dumps({
        'kind': 1,
        'id': '34cd',
        'pubkey': '98fe',
        'content': 'The orig post',
        'created_at': THEN_TS,
        'tags': [],
      }, sort_keys=True),
      'tags': [
        ['e', '34cd', 'TODO relay', 'mention'],
        ['p', '98fe'],
      ],
      'created_at': NOW_TS,
    }

    self.assertEqual(repost, to_as1(event))
    self.assertEqual(event, from_as1(repost))

    del event['content']
    self.assertEqual({
      **repost,
      'object': 'nostr:note1xnxs50q044',
    }, to_as1(event))

  def test_to_from_as1_like(self):
    like = {
      'objectType': 'activity',
      'verb': 'like',
      'id': 'nostr:nevent1z24spd6d40',
      'published': NOW_ISO,
      'object': 'nostr:nevent1xnxsm5fasn',
    }
    event = {
      'kind': 7,
      'id': '12ab',
      'content': '+',
      'tags': [['e', '34cd']],
      'created_at': NOW_TS,
    }

    self.assertEqual(like, to_as1(event))
    self.assertEqual(event, from_as1(like))

  def test_to_from_as1_dislike(self):
    like = {
      'objectType': 'activity',
      'verb': 'dislike',
      'id': 'nostr:nevent1z24spd6d40',
      'published': NOW_ISO,
      'object': 'nostr:nevent1xnxsm5fasn',
    }
    event = {
      'kind': 7,
      'id': '12ab',
      'content': '-',
      'tags': [['e', '34cd']],
      'created_at': NOW_TS,
    }

    self.assertEqual(like, to_as1(event))
    self.assertEqual(event, from_as1(like))

  def test_to_from_as1_reaction(self):
    react = {
      'objectType': 'activity',
      'verb': 'react',
      'id': 'nostr:nevent1z24spd6d40',
      'content': '😀',
      'published': NOW_ISO,
      'object': 'nostr:nevent1xnxsm5fasn',
    }
    event = {
      'kind': 7,
      'id': '12ab',
      'content': '😀',
      'tags': [['e', '34cd']],
      'created_at': NOW_TS,
    }

    self.assertEqual(react, to_as1(event))
    self.assertEqual(event, from_as1(react))

  def test_to_from_as1_delete(self):
    delete = {
      'objectType': 'activity',
      'verb': 'delete',
      'id': 'nostr:nevent1z24spd6d40',
      'published': NOW_ISO,
      'object': 'nostr:nevent1xnxsm5fasn',
      'content': 'a note about the delete',
    }
    event = {
      'kind': 5,
      'id': '12ab',
      'content': 'a note about the delete',
      'tags': [['e', '34cd']],
      'created_at': NOW_TS,
    }

    self.assertEqual(delete, to_as1(event))
    self.assertEqual(event, from_as1(delete))

  def test_to_from_as1_followings(self):
    follow = {
      'objectType': 'activity',
      'verb': 'follow',
      'id': 'nostr:nevent1z24spd6d40',
      'published': NOW_ISO,
      'object': [
        'nostr:npub1xnxsce33j3',
        {'id': 'nostr:npub1nrlqrdny0w', 'displayName': 'bob'},
      ],
      'content': 'not important',
    }
    event = {
      'kind': 3,
      'id': '12ab',
      'content': 'not important',
      'tags': [
        ['p', '34cd', 'TODO relay', ''],
        ['p', '98fe', 'TODO relay', 'bob'],
      ],
      'created_at': NOW_TS,
    }

    self.assertEqual(follow, to_as1(event))
    self.assertEqual(event, from_as1(follow))

  def test_get_activities_user_id(self):
    self.mox.StubOutWithMock(secrets, 'token_urlsafe')
    secrets.token_urlsafe(16).AndReturn('towkin')
    self.mox.ReplayAll()

    events = [{
      **NOTE_NOSTR,
      'content': f"It's {i}",
    } for i in range(3)]
    notes = [{
      **NOTE_AS1,
      'content': f"It's {i}",
    } for i in range(3)]

    FakeConnection.receive = [
      ['EOSE', 'towkin'],
    ] + [
      ['EVENT', 'towkin', event] for event in events
    ]

    n = nostr.Nostr(['ws://relay'])
    self.assert_equals(notes, n.get_activities(user_id='ab12'))

    self.assertEqual('ws://relay', FakeConnection.relay)
    self.assertEqual([['REQ', 'towkin', {
      'authors': ['ab12'],
      'limit': 10,
    }]], FakeConnection.sent)
    self.assertEqual([], FakeConnection.receive)
