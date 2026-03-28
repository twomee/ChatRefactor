package handler

import (
	"regexp"
	"strings"
)

var mentionRegex = regexp.MustCompile(`@(\w+)`)

// roomMentionRegex matches @room, @channel, or @everyone only when they appear
// as whole words (i.e. not as a prefix of a longer word like @roommate).
var roomMentionRegex = regexp.MustCompile(`(?i)@(room|channel|everyone)\b`)

// parseMentions extracts @usernames from message text.
// Returns a deduplicated, lowercased slice of mentioned usernames.
func parseMentions(text string) []string {
	matches := mentionRegex.FindAllStringSubmatch(text, -1)
	seen := make(map[string]bool)
	mentions := make([]string, 0)
	for _, match := range matches {
		username := strings.ToLower(match[1])
		if !seen[username] {
			seen[username] = true
			mentions = append(mentions, username)
		}
	}
	return mentions
}

// isRoomMention returns true if text contains @room, @channel, or @everyone.
func isRoomMention(text string) bool {
	return roomMentionRegex.MatchString(text)
}
