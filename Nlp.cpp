#include "Nlp.h"
#include <iostream>
#include <fstream>

// ── helper functions ──────────────────────────────────────────────────────────

static int myStrlen(const char* s) {
    if (!s) return 0;
    int n = 0;
    while (s[n]) n++;
    return n;
}

static bool myStrcmp(const char* a, const char* b) {
    if (!a || !b) return false;
    int i = 0;
    while (a[i] && b[i]) {
        if (a[i] != b[i]) return false;
        i++;
    }
    return a[i] == '\0' && b[i] == '\0';
}

static void myStrcpy(char* dst, const char* src) {
    if (!dst || !src) return;
    int i = 0;
    while (src[i]) { dst[i] = src[i]; i++; }
    dst[i] = '\0';
}

static bool myIsAlpha(char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
}

static bool myIsAlnum(char c) {
    return myIsAlpha(c) || (c >= '0' && c <= '9');
}

static char myToLower(char c) {
    if (c >= 'A' && c <= 'Z') return (char)(c - 'A' + 'a');
    return c;
}

static bool myStrcmpCI(const char* a, const char* b) {
    if (!a || !b) return false;
    int i = 0;
    while (a[i] && b[i]) {
        if (myToLower(a[i]) != myToLower(b[i])) return false;
        i++;
    }
    return a[i] == '\0' && b[i] == '\0';
}

// ── NLP functions ─────────────────────────────────────────────────────────────

int NLP::countTokens(const char* filename) {
    if (!filename) return 0;
    std::ifstream file(filename);
    if (!file.is_open()) return 0;

    int count = 0;
    char word[1024];
    while (file >> word) count++;
    file.close();
    return count;
}

int NLP::countSentences(const char* filename) {
    if (!filename) return 0;
    std::ifstream file(filename);
    if (!file.is_open()) return 0;

    int count = 0;
    int dotCount = 0;
    char c;

    while (file.get(c)) {
        if (c == '.') {
            dotCount++;
        } else {
            if (dotCount > 0) {
                // 3+ consecutive dots = ellipsis = 1 sentence; otherwise each dot = 1 sentence
                count += (dotCount >= 3) ? 1 : dotCount;
                dotCount = 0;
            }
            if (c == '!' || c == '?') count++;
        }
    }
    if (dotCount > 0)
        count += (dotCount >= 3) ? 1 : dotCount;

    file.close();
    return count;
}

void NLP::sanitise(const char* src, char* dest) {
    if (!src || !dest) return;

    int len = myStrlen(src);
    int di = 0;

    for (int i = 0; i < len; i++) {
        char c = src[i];
        if (myIsAlnum(c)) {
            dest[di++] = c;
        } else if (c == '-') {
            // keep hyphen in compound words (flanked by alphanumeric chars)
            if (i > 0 && i < len - 1 && myIsAlnum(src[i - 1]) && myIsAlnum(src[i + 1]))
                dest[di++] = c;
        }
    }
    dest[di] = '\0';
}

void NLP::replaceAndTransfer(const char* srcname, const char* destname, const char* mapname) {
    if (!srcname || !destname || !mapname) return;

    std::ifstream mapFile(mapname);
    if (!mapFile.is_open()) return;

    const int MAX_PAIRS = 1000;
    const int MAX_WORD  = 512;

    char keys[MAX_PAIRS][MAX_WORD];
    char vals[MAX_PAIRS][MAX_WORD];
    int  pairCount = 0;

    char k[MAX_WORD], v[MAX_WORD];
    while (pairCount < MAX_PAIRS && (mapFile >> k) && (mapFile >> v)) {
        myStrcpy(keys[pairCount], k);
        myStrcpy(vals[pairCount], v);
        pairCount++;
    }
    mapFile.close();

    std::ifstream srcFile(srcname);
    if (!srcFile.is_open()) return;

    std::ofstream destFile(destname);
    if (!destFile.is_open()) { srcFile.close(); return; }

    // Read character by character; accumulate non-whitespace tokens,
    // flush them (with possible replacement) on whitespace.
    char token[MAX_WORD];
    int  ti = 0;
    char c;

    while (srcFile.get(c)) {
        if (c == ' ' || c == '\n' || c == '\t' || c == '\r') {
            if (ti > 0) {
                token[ti] = '\0';
                bool replaced = false;
                for (int i = 0; i < pairCount; i++) {
                    if (myStrcmp(token, keys[i])) {
                        destFile << vals[i];
                        replaced = true;
                        break;
                    }
                }
                if (!replaced) destFile << token;
                ti = 0;
            }
            destFile << c;
        } else {
            token[ti++] = c;
        }
    }
    // flush last token
    if (ti > 0) {
        token[ti] = '\0';
        bool replaced = false;
        for (int i = 0; i < pairCount; i++) {
            if (myStrcmp(token, keys[i])) {
                destFile << vals[i];
                replaced = true;
                break;
            }
        }
        if (!replaced) destFile << token;
    }

    srcFile.close();
    destFile.close();
}

bool NLP::isStopWord(const char* word) {
    if (!word) return false;

    const char* stops[] = {"the", "and", "is", "of", "to", "a"};
    for (int i = 0; i < 6; i++) {
        if (myStrcmpCI(word, stops[i])) return true;
    }
    return false;
}

void NLP::extractVocabulary(const char* srcname, const char* destname) {
    if (!srcname || !destname) return;

    std::ifstream srcFile(srcname);
    if (!srcFile.is_open()) return;

    const int MAX_VOCAB = 10000;
    const int MAX_WORD  = 512;

    char vocab[MAX_VOCAB][MAX_WORD];
    int  vocabCount = 0;

    // Load words already present in dest so we can check for duplicates
    std::ifstream existDest(destname);
    if (existDest.is_open()) {
        char existing[MAX_WORD];
        while (vocabCount < MAX_VOCAB && (existDest >> existing))
            myStrcpy(vocab[vocabCount++], existing);
        existDest.close();
    }

    std::ofstream destFile(destname, std::ios::app);
    if (!destFile.is_open()) { srcFile.close(); return; }

    char word[MAX_WORD];
    char sanitised[MAX_WORD];
    char lower[MAX_WORD];

    while (srcFile >> word) {
        sanitise(word, sanitised);

        int len = myStrlen(sanitised);
        if (len < 4) continue;

        for (int i = 0; i <= len; i++)
            lower[i] = myToLower(sanitised[i]);

        if (isStopWord(lower)) continue;

        bool found = false;
        for (int i = 0; i < vocabCount; i++) {
            if (myStrcmp(vocab[i], lower)) { found = true; break; }
        }

        if (!found && vocabCount < MAX_VOCAB) {
            myStrcpy(vocab[vocabCount++], lower);
            destFile << lower << '\n';
        }
    }

    srcFile.close();
    destFile.close();
}

void NLP::charFrequency(const char* filename) {
    if (!filename) return;

    std::ifstream inFile(filename);
    if (!inFile.is_open()) return;

    int freq[26] = {0};
    char c;
    while (inFile.get(c)) {
        if (myIsAlpha(c))
            freq[(int)(myToLower(c) - 'a')]++;
    }
    inFile.close();

    std::ofstream outFile(filename, std::ios::app);
    if (!outFile.is_open()) return;

    outFile << '\n';
    outFile << "Character Frequencies:\n";
    for (int i = 0; i < 26; i++)
        outFile << (char)('A' + i) << ": " << freq[i] << '\n';

    outFile.close();
}

void NLP::generateNGrams(const char* filename, int n) {
    if (!filename) return;
    if (n < 1 || n > 10) return;

    std::ifstream file(filename);
    if (!file.is_open()) return;

    const int MAX_TOKENS = 10000;
    const int MAX_WORD   = 512;

    char tokens[MAX_TOKENS][MAX_WORD];
    int  tokenCount = 0;

    char word[MAX_WORD];
    char sanitised[MAX_WORD];

    while (tokenCount < MAX_TOKENS && (file >> word)) {
        sanitise(word, sanitised);
        if (myStrlen(sanitised) > 0)
            myStrcpy(tokens[tokenCount++], sanitised);
    }
    file.close();

    if (tokenCount < n) return;

    // Build gram name
    char gramName[16];
    if (n == 1) {
        myStrcpy(gramName, "Unigram");
    } else if (n == 2) {
        myStrcpy(gramName, "Bigram");
    } else if (n == 3) {
        myStrcpy(gramName, "Trigram");
    } else {
        // "n-gram" for n 4..10
        int gi = 0;
        if (n == 10) {
            gramName[gi++] = '1';
            gramName[gi++] = '0';
        } else {
            gramName[gi++] = (char)('0' + n);
        }
        gramName[gi++] = '-';
        gramName[gi++] = 'g';
        gramName[gi++] = 'r';
        gramName[gi++] = 'a';
        gramName[gi++] = 'm';
        gramName[gi]   = '\0';
    }

    for (int i = 0; i <= tokenCount - n; i++) {
        std::cout << gramName << ": [";
        for (int j = 0; j < n; j++) {
            if (j > 0) std::cout << ' ';
            std::cout << tokens[i + j];
        }
        std::cout << "]\n";
    }
}

bool NLP::containsKeyword(const char* filename, const char* keyword) {
    if (!filename || !keyword) return false;

    std::ifstream file(filename);
    if (!file.is_open()) return false;

    int kwLen = myStrlen(keyword);
    if (kwLen == 0) { file.close(); return false; }

    char word[4096];
    while (file >> word) {
        int wLen = myStrlen(word);
        for (int i = 0; i <= wLen - kwLen; i++) {
            bool match = true;
            for (int j = 0; j < kwLen; j++) {
                if (word[i + j] != keyword[j]) { match = false; break; }
            }
            if (match) { file.close(); return true; }
        }
    }

    file.close();
    return false;
}
