#ifndef NLP_H
#define NLP_H

namespace NLP {
    int countTokens(const char* filename);
    int countSentences(const char* filename);
    void sanitise(const char* src, char* dest);
    void replaceAndTransfer(const char* srcname, const char* destname, const char* mapname);
    bool isStopWord(const char* word);
    void extractVocabulary(const char* srcname, const char* destname);
    void charFrequency(const char* filename);
    void generateNGrams(const char* filename, int n);
    bool containsKeyword(const char* filename, const char* keyword);
}

#endif
