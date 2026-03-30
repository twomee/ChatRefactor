package handler

import (
	"testing"
)

func TestParseMentions_SingleMention(t *testing.T) {
	mentions := parseMentions("hello @alice how are you?")
	if len(mentions) != 1 || mentions[0] != "alice" {
		t.Errorf("expected [alice], got %v", mentions)
	}
}

func TestParseMentions_MultipleMentions(t *testing.T) {
	mentions := parseMentions("@alice and @bob check this out @charlie")
	if len(mentions) != 3 {
		t.Errorf("expected 3 mentions, got %d: %v", len(mentions), mentions)
	}
	expected := []string{"alice", "bob", "charlie"}
	for i, e := range expected {
		if mentions[i] != e {
			t.Errorf("mentions[%d] = %q, want %q", i, mentions[i], e)
		}
	}
}

func TestParseMentions_Deduplication(t *testing.T) {
	mentions := parseMentions("@alice hey @Alice come here @ALICE")
	if len(mentions) != 1 || mentions[0] != "alice" {
		t.Errorf("expected [alice], got %v", mentions)
	}
}

func TestParseMentions_NoMentions(t *testing.T) {
	mentions := parseMentions("just a regular message")
	if len(mentions) != 0 {
		t.Errorf("expected empty, got %v", mentions)
	}
}

func TestParseMentions_EmptyString(t *testing.T) {
	mentions := parseMentions("")
	if len(mentions) != 0 {
		t.Errorf("expected empty, got %v", mentions)
	}
}

func TestParseMentions_UnderscoreUsername(t *testing.T) {
	mentions := parseMentions("hey @user_name check this")
	if len(mentions) != 1 || mentions[0] != "user_name" {
		t.Errorf("expected [user_name], got %v", mentions)
	}
}

func TestIsRoomMention_Room(t *testing.T) {
	if !isRoomMention("hey @room check this") {
		t.Error("expected true for @room")
	}
}

func TestIsRoomMention_Channel(t *testing.T) {
	if !isRoomMention("@channel important update") {
		t.Error("expected true for @channel")
	}
}

func TestIsRoomMention_Everyone(t *testing.T) {
	if !isRoomMention("@everyone please read") {
		t.Error("expected true for @everyone")
	}
}

func TestIsRoomMention_CaseInsensitive(t *testing.T) {
	if !isRoomMention("Hey @ROOM check this") {
		t.Error("expected true for @ROOM (case-insensitive)")
	}
}

func TestIsRoomMention_NoRoomMention(t *testing.T) {
	if isRoomMention("hello @alice no room mention here") {
		t.Error("expected false for regular mention")
	}
}

func TestIsRoomMention_EmptyString(t *testing.T) {
	if isRoomMention("") {
		t.Error("expected false for empty string")
	}
}
