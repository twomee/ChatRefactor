package handler

import (
	"regexp"
	"strings"
)

var mentionRegex = regexp.MustCompile(`@(\w+)`)

// parseMentions extracts @usernames from message text.
// Returns a deduplicated, lowercased slice of mentioned usernames.
func parseMentions(text string) []string {
	matches := mentionRegex.FindAllStringSubmatch(text, -1)
	seen := make(map[string]bool)
	var mentions []string
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
	lower := strings.ToLower(text)
	return strings.Contains(lower, "@room") ||
		strings.Contains(lower, "@channel") ||
		strings.Contains(lower, "@everyone")
}
