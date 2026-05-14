#include "Nlp.h"
#include <iostream>
#include <fstream>

// ── tiny assertion helper ─────────────────────────────────────────────────────

static int passed = 0;
static int failed = 0;

static void check(bool condition, const char* label) {
    if (condition) {
        std::cout << "[PASS] " << label << '\n';
        passed++;
    } else {
        std::cout << "[FAIL] " << label << '\n';
        failed++;
    }
}

// ── helpers to create temp files ─────────────────────────────────────────────

static void writeFile(const char* name, const char* content) {
    std::ofstream f(name);
    if (f.is_open()) f << content;
}

static bool fileContains(const char* name, const char* needle) {
    std::ifstream f(name);
    if (!f.is_open()) return false;
    char line[4096];
    int needleLen = 0;
    while (needle[needleLen]) needleLen++;
    while (f.getline(line, 4096)) {
        int lineLen = 0;
        while (line[lineLen]) lineLen++;
        for (int i = 0; i <= lineLen - needleLen; i++) {
            bool ok = true;
            for (int j = 0; j < needleLen; j++) {
                if (line[i + j] != needle[j]) { ok = false; break; }
            }
            if (ok) return true;
        }
    }
    return false;
}

// ── countTokens ───────────────────────────────────────────────────────────────

static void testCountTokens() {
    writeFile("t_tokens.txt", "hello world foo bar");
    check(NLP::countTokens("t_tokens.txt") == 4, "countTokens: 4 words");

    writeFile("t_tokens2.txt", "one\ntwo\nthree");
    check(NLP::countTokens("t_tokens2.txt") == 3, "countTokens: newline-separated words");

    writeFile("t_empty.txt", "");
    check(NLP::countTokens("t_empty.txt") == 0, "countTokens: empty file");

    check(NLP::countTokens(0) == 0, "countTokens: NULL filename");
    check(NLP::countTokens("no_such_file.txt") == 0, "countTokens: non-existent file");

    writeFile("t_tokens3.txt", "single");
    check(NLP::countTokens("t_tokens3.txt") == 1, "countTokens: single token");
}

// ── countSentences ────────────────────────────────────────────────────────────

static void testCountSentences() {
    writeFile("t_sent1.txt", "Hello world. How are you? I am fine!");
    check(NLP::countSentences("t_sent1.txt") == 3, "countSentences: . ? !");

    writeFile("t_sent2.txt", "Wait... Really! Yes.");
    check(NLP::countSentences("t_sent2.txt") == 3, "countSentences: ellipsis counts as 1");

    writeFile("t_sent3.txt", "");
    check(NLP::countSentences("t_sent3.txt") == 0, "countSentences: empty file");

    check(NLP::countSentences(0) == 0, "countSentences: NULL filename");
    check(NLP::countSentences("no_such.txt") == 0, "countSentences: non-existent file");

    writeFile("t_sent4.txt", "One. Two. Three.");
    check(NLP::countSentences("t_sent4.txt") == 3, "countSentences: 3 plain sentences");

    writeFile("t_sent5.txt", "End...");
    check(NLP::countSentences("t_sent5.txt") == 1, "countSentences: trailing ellipsis");
}

// ── sanitise ─────────────────────────────────────────────────────────────────

static void testSanitise() {
    char dest[256];

    NLP::sanitise("hello!", dest);
    check(dest[0]=='h' && dest[1]=='e' && dest[2]=='l' && dest[3]=='l' && dest[4]=='o' && dest[5]=='\0',
          "sanitise: removes trailing punctuation");

    NLP::sanitise("well-known", dest);
    check(dest[0]=='w' && dest[4]=='-' && dest[5]=='k', "sanitise: keeps hyphen in compound word");

    NLP::sanitise("abc123", dest);
    check(dest[0]=='a' && dest[5]=='3' && dest[6]=='\0', "sanitise: alphanumeric unchanged");

    NLP::sanitise("!@#$%", dest);
    check(dest[0] == '\0', "sanitise: all non-alnum becomes empty string");

    NLP::sanitise(0, dest);   // should not crash
    check(true, "sanitise: NULL src does not crash");

    NLP::sanitise("hello", 0); // should not crash
    check(true, "sanitise: NULL dest does not crash");

    NLP::sanitise("-leading", dest);
    // leading hyphen: no alnum before it, should be dropped
    check(dest[0] == 'l', "sanitise: leading hyphen removed");

    NLP::sanitise("trailing-", dest);
    // trailing hyphen: no alnum after it, should be dropped
    int len = 0; while (dest[len]) len++;
    check(dest[len - 1] == 'g', "sanitise: trailing hyphen removed");
}

// ── isStopWord ────────────────────────────────────────────────────────────────

static void testIsStopWord() {
    check(NLP::isStopWord("the"),  "isStopWord: 'the'");
    check(NLP::isStopWord("THE"),  "isStopWord: 'THE' (case insensitive)");
    check(NLP::isStopWord("and"),  "isStopWord: 'and'");
    check(NLP::isStopWord("Is"),   "isStopWord: 'Is'");
    check(NLP::isStopWord("of"),   "isStopWord: 'of'");
    check(NLP::isStopWord("TO"),   "isStopWord: 'TO'");
    check(NLP::isStopWord("a"),    "isStopWord: 'a'");
    check(!NLP::isStopWord("cat"), "isStopWord: 'cat' is not a stop word");
    check(!NLP::isStopWord(0),     "isStopWord: NULL returns false");
    check(!NLP::isStopWord(""),    "isStopWord: empty string returns false");
}

// ── containsKeyword ───────────────────────────────────────────────────────────

static void testContainsKeyword() {
    writeFile("t_kw.txt", "The quick brown fox jumps over the lazy dog");

    check(NLP::containsKeyword("t_kw.txt", "fox"),    "containsKeyword: word present");
    check(NLP::containsKeyword("t_kw.txt", "dog"),    "containsKeyword: last word");
    check(NLP::containsKeyword("t_kw.txt", "The"),    "containsKeyword: first word");
    check(!NLP::containsKeyword("t_kw.txt", "cat"),   "containsKeyword: absent word");
    check(!NLP::containsKeyword("t_kw.txt", "FOX"),   "containsKeyword: case-sensitive mismatch");
    check(!NLP::containsKeyword(0, "fox"),             "containsKeyword: NULL filename");
    check(!NLP::containsKeyword("t_kw.txt", 0),        "containsKeyword: NULL keyword");
    check(!NLP::containsKeyword("no_file.txt", "fox"), "containsKeyword: non-existent file");
}

// ── replaceAndTransfer ────────────────────────────────────────────────────────

static void testReplaceAndTransfer() {
    writeFile("t_src.txt",  "The 8th assignment for INF134 is on const char pointers.\n");
    writeFile("t_map.txt",  "assignment practical\nINF134 COS132\n");

    NLP::replaceAndTransfer("t_src.txt", "t_dest.txt", "t_map.txt");
    check(fileContains("t_dest.txt", "practical"),  "replaceAndTransfer: word replaced");
    check(fileContains("t_dest.txt", "COS132"),     "replaceAndTransfer: second replacement");
    check(!fileContains("t_dest.txt", "assignment"),"replaceAndTransfer: original word absent");
    check(fileContains("t_dest.txt", "pointers."),  "replaceAndTransfer: punctuation preserved");

    // NULL guard
    NLP::replaceAndTransfer(0, "t_dest.txt", "t_map.txt");
    check(true, "replaceAndTransfer: NULL src does not crash");
    NLP::replaceAndTransfer("t_src.txt", "t_dest.txt", 0);
    check(true, "replaceAndTransfer: NULL map does not crash");

    // Non-existent files
    NLP::replaceAndTransfer("no_src.txt", "t_dest.txt", "t_map.txt");
    check(true, "replaceAndTransfer: missing src does not crash");
}

// ── extractVocabulary ─────────────────────────────────────────────────────────

static void testExtractVocabulary() {
    writeFile("t_vocab_src.txt",
              "The 8th practical for COS132 is on const char pointers and file streams\n");

    // Remove output file if it exists so we start fresh
    {
        std::ofstream clear("t_vocab_dst.txt");
    }

    NLP::extractVocabulary("t_vocab_src.txt", "t_vocab_dst.txt");

    check(fileContains("t_vocab_dst.txt", "practical"),  "extractVocabulary: 'practical' included");
    check(fileContains("t_vocab_dst.txt", "pointers"),   "extractVocabulary: 'pointers' included");
    check(fileContains("t_vocab_dst.txt", "streams"),    "extractVocabulary: 'streams' included");
    check(!fileContains("t_vocab_dst.txt", "the"),       "extractVocabulary: stop word 'the' excluded");
    check(!fileContains("t_vocab_dst.txt", "and"),       "extractVocabulary: stop word 'and' excluded");
    check(!fileContains("t_vocab_dst.txt", "is"),        "extractVocabulary: stop word 'is' excluded");
    // "8th" sanitises to "8th" (3 chars) -> excluded by length
    check(!fileContains("t_vocab_dst.txt", "8th"),       "extractVocabulary: short token excluded");

    // Duplicate call should not add again
    NLP::extractVocabulary("t_vocab_src.txt", "t_vocab_dst.txt");
    // Count lines to verify no duplicates
    std::ifstream f("t_vocab_dst.txt");
    int lines = 0;
    char buf[512];
    while (f.getline(buf, 512)) { if (buf[0]) lines++; }
    f.close();
    check(lines == NLP::countTokens("t_vocab_dst.txt"), "extractVocabulary: no duplicates on second call");

    // NULL guards
    NLP::extractVocabulary(0, "t_vocab_dst.txt");
    check(true, "extractVocabulary: NULL src does not crash");
    NLP::extractVocabulary("t_vocab_src.txt", 0);
    check(true, "extractVocabulary: NULL dest does not crash");
}

// ── charFrequency ─────────────────────────────────────────────────────────────

static void testCharFrequency() {
    writeFile("t_freq.txt", "Hello World\n");

    NLP::charFrequency("t_freq.txt");

    check(fileContains("t_freq.txt", "Character Frequencies:"), "charFrequency: heading appended");
    check(fileContains("t_freq.txt", "H"),   "charFrequency: frequency table present");
    check(fileContains("t_freq.txt", "Hello World"), "charFrequency: original content preserved");

    // NULL guard
    NLP::charFrequency(0);
    check(true, "charFrequency: NULL filename does not crash");
    NLP::charFrequency("no_such_file.txt");
    check(true, "charFrequency: non-existent file does not crash");
}

// ── generateNGrams ────────────────────────────────────────────────────────────

static void testGenerateNGrams() {
    writeFile("t_ngram.txt",
              "The 8th practical for COS132 is on const char pointers and file streams\n");

    std::cout << "\n--- Unigrams ---\n";
    NLP::generateNGrams("t_ngram.txt", 1);
    std::cout << "\n--- Bigrams ---\n";
    NLP::generateNGrams("t_ngram.txt", 2);
    std::cout << "\n--- Trigrams ---\n";
    NLP::generateNGrams("t_ngram.txt", 3);
    std::cout << "\n--- 4-grams ---\n";
    NLP::generateNGrams("t_ngram.txt", 4);

    // n > token count: should produce no output (no crash)
    writeFile("t_short.txt", "one two");
    std::cout << "\n--- 7-gram on 2-word file (no output expected) ---\n";
    NLP::generateNGrams("t_short.txt", 7);
    check(true, "generateNGrams: n > tokenCount does not crash");

    // NULL / bad inputs
    NLP::generateNGrams(0, 2);
    check(true, "generateNGrams: NULL filename does not crash");
    NLP::generateNGrams("no_file.txt", 2);
    check(true, "generateNGrams: non-existent file does not crash");
    NLP::generateNGrams("t_ngram.txt", 0);
    check(true, "generateNGrams: n=0 does not crash");
    NLP::generateNGrams("t_ngram.txt", 11);
    check(true, "generateNGrams: n>10 does not crash");
}

// ── main ──────────────────────────────────────────────────────────────────────

int main() {
    std::cout << "=== countTokens ===\n";
    testCountTokens();

    std::cout << "\n=== countSentences ===\n";
    testCountSentences();

    std::cout << "\n=== sanitise ===\n";
    testSanitise();

    std::cout << "\n=== isStopWord ===\n";
    testIsStopWord();

    std::cout << "\n=== containsKeyword ===\n";
    testContainsKeyword();

    std::cout << "\n=== replaceAndTransfer ===\n";
    testReplaceAndTransfer();

    std::cout << "\n=== extractVocabulary ===\n";
    testExtractVocabulary();

    std::cout << "\n=== charFrequency ===\n";
    testCharFrequency();

    std::cout << "\n=== generateNGrams ===\n";
    testGenerateNGrams();

    std::cout << "\n===========================\n";
    std::cout << "Passed: " << passed << '\n';
    std::cout << "Failed: " << failed << '\n';
    return 0;
}
