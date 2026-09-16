/* wordcount: read stdin, print "<lines> <words> <chars>".
 * The implementation of this claim -- deliberately ordinary code, built by a
 * compiler rather than regrown by a model. */
#include <ctype.h>
#include <stdio.h>

int main(void) {
    long lines = 0, words = 0, chars = 0;
    int c, in_word = 0;
    while ((c = getchar()) != EOF) {
        chars++;
        if (c == '\n') lines++;
        if (isspace(c)) in_word = 0;
        else if (!in_word) { in_word = 1; words++; }
    }
    printf("%ld %ld %ld\n", lines, words, chars);
    return 0;
}
