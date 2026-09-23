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

module.exports = { FAKE_ARCHIVE, FAKE_MANIFEST, FAKE_CS_INDEX };
