"use strict";
// Invented data only. No archive record, quote, reporter or URL in this file
// comes from the real HoopsHype rumors archive.

const FAKE_ARCHIVE = [
  {
    archive_date: "2999-01-05", outlet: "Fake Wire", reporter: "Fake Reporter",
    source_url: "https://example.com/wire/one?utm_source=x",
    tags: ["Fake Player", "Example Owls", "Trade"],
    text: "Fake Player and the Example Owls have opened extension talks, with a deal worth nearly 60 million dollars on the table.",
    quote: "We are talking, and we are close.",
  },
  {
    archive_date: "2999-01-04", outlet: "Example Daily", reporter: "Second Reporter",
    source_url: "https://example.org/news/two",
    tags: ["Fake Player", "Example Owls"],
    text: "The Example Owls must decide by Jan. 20 whether to guarantee the third year of the contract.",
    quote: "",
  },
  {
    archive_date: "2999-01-03", outlet: "", reporter: "",
    source_url: "https://example.net/social/",
    tags: ["Fake Player"],
    text: "Fake Player: I like it here and I want to stay.",
    quote: "I like it here and I want to stay.",
  },
];

const FAKE_MANIFEST = {
  players: [{ name: "Fake Player", slug: "fake-player" }],
  teams: [{ name: "Example Owls", slug: "example-owls" }],
};

const FAKE_CS_INDEX = {
  items: [
    {
      id: "a1", source: "bluesky", author: "Fake Poster", author_handle: "fakeposter",
      published_at: "2999-01-05T12:00:00Z", url: "https://bsky.example/post/1",
      title: "", body_excerpt: "Fake Player extension talks are moving, say two people briefed on them.",
    },
    {
      id: "a2", source: "youtube", channel: "Example Hoops Show",
      published_at: "2999-01-04T12:00:00Z", url: "https://youtube.com/watch?v=fake1",
      title: "Breaking down the Fake Player extension talks in full", body_excerpt: "A long look at the numbers.",
    },
  ],
};

// --- v7: content-stream fixtures for the primary-entity rule ---------------
// One invented player, one invented team, and two index files whose items say
// which of the two they are about. Nothing here is a real account, channel,
// post or URL.
const V7_CS_MANIFEST = {
  players: [{ name: "Fake Player", slug: "fake-player" }],
  teams: [{ name: "Example Owls", slug: "example-owls" }],
};

// n items that name Fake Player (and never the team).
function v7PersonItems(n) {
  const items = [];
  for (let i = 0; i < n; i++) {
    items.push({
      id: `p${i}`, source: "bluesky",
      // A distinct handle per item: one item per voice is an existing rule.
      author: `Fake Poster ${i}`, author_handle: `fakeposter${i}`,
      published_at: `2999-01-0${5 - (i % 5)}T12:00:00Z`,
      url: `https://bsky.example/person/${i}`,
      title: `Fake Player extension talks keep moving forward ${i}`,
      body_excerpt: "A look at where the extension talks stand.",
    });
  }
  return items;
}

// n items that name the Example Owls and never Fake Player.
function v7TeamItems(n) {
  const items = [];
  for (let i = 0; i < n; i++) {
    items.push({
      id: `t${i}`, source: "bluesky",
      author: `Example Poster ${i}`, author_handle: `exampleposter${i}`,
      published_at: `2999-01-0${5 - (i % 5)}T09:00:00Z`,
      url: `https://bsky.example/team/${i}`,
      title: `Example Owls rotation questions heading into camp ${i}`,
      body_excerpt: "Notes on how the Owls plan to use their bench.",
    });
  }
  return items;
}

// --- v8: an aggregator/bot account in the content stream -------------------
// An invented bot handle on an item that would otherwise pass every filter, so
// a demo can show it being dropped for the handle and nothing else.
function v8BotItems(n) {
  const items = [];
  for (let i = 0; i < n; i++) {
    items.push({
      id: `b${i}`, source: "bluesky",
      author: "Fake Shams Bot", author_handle: i === 0 ? "shamsbot" : `fakerumorbot${i}`,
      published_at: "2999-01-05T18:00:00Z",
      url: `https://bsky.example/bot/${i}`,
      title: `Fake Player extension talks reported by an account ${i}`,
      body_excerpt: "A repost of somebody else's reporting.",
    });
  }
  return items;
}

module.exports = {
  FAKE_ARCHIVE, FAKE_MANIFEST, FAKE_CS_INDEX,
  V7_CS_MANIFEST, v7PersonItems, v7TeamItems, v8BotItems,
};
