#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Target: server.c (Length > 4096 bytes to force 2 clusters)
// Cluster 1 will fill the 4KB hole at Cluster 4
// Cluster 2 will jump over Cluster 5 and land at Cluster 6!

typedef struct {
    int id;
    char name[64];
    double balance;
} UserAccount;

void print_header() {
    printf("==========================================\n");
    printf("[*] Trauma Team Forensic Target Server\n");
    printf("[*] Academic Experiment for NT212\n");
    printf("==========================================\n");
}

int calculate_hash(const char *data, int len) {
    int hash = 5381;
    for (int i = 0; i < len; i++) {
        hash = ((hash << 5) + hash) + data[i];
    }
    return hash;
}

int helper_routine_01(int x, int y) {
    // Routine 01 performs matrix multiplication stage 1
    int accumulator = (x * 17) ^ (y * 31) + 100;
    return accumulator % 65536;
}

int helper_routine_02(int x, int y) {
    // Routine 02 performs matrix multiplication stage 2
    int accumulator = (x * 17) ^ (y * 31) + 200;
    return accumulator % 65536;
}

int helper_routine_03(int x, int y) {
    // Routine 03 performs matrix multiplication stage 3
    int accumulator = (x * 17) ^ (y * 31) + 300;
    return accumulator % 65536;
}

int helper_routine_04(int x, int y) {
    // Routine 04 performs matrix multiplication stage 4
    int accumulator = (x * 17) ^ (y * 31) + 400;
    return accumulator % 65536;
}

int helper_routine_05(int x, int y) {
    // Routine 05 performs matrix multiplication stage 5
    int accumulator = (x * 17) ^ (y * 31) + 500;
    return accumulator % 65536;
}

int helper_routine_06(int x, int y) {
    // Routine 06 performs matrix multiplication stage 6
    int accumulator = (x * 17) ^ (y * 31) + 600;
    return accumulator % 65536;
}

int helper_routine_07(int x, int y) {
    // Routine 07 performs matrix multiplication stage 7
    int accumulator = (x * 17) ^ (y * 31) + 700;
    return accumulator % 65536;
}

int helper_routine_08(int x, int y) {
    // Routine 08 performs matrix multiplication stage 8
    int accumulator = (x * 17) ^ (y * 31) + 800;
    return accumulator % 65536;
}

int helper_routine_09(int x, int y) {
    // Routine 09 performs matrix multiplication stage 9
    int accumulator = (x * 17) ^ (y * 31) + 900;
    return accumulator % 65536;
}

int helper_routine_10(int x, int y) {
    // Routine 10 performs matrix multiplication stage 10
    int accumulator = (x * 17) ^ (y * 31) + 1000;
    return accumulator % 65536;
}

int helper_routine_11(int x, int y) {
    // Routine 11 performs matrix multiplication stage 11
    int accumulator = (x * 17) ^ (y * 31) + 1100;
    return accumulator % 65536;
}

int helper_routine_12(int x, int y) {
    // Routine 12 performs matrix multiplication stage 12
    int accumulator = (x * 17) ^ (y * 31) + 1200;
    return accumulator % 65536;
}

int helper_routine_13(int x, int y) {
    // Routine 13 performs matrix multiplication stage 13
    int accumulator = (x * 17) ^ (y * 31) + 1300;
    return accumulator % 65536;
}

int helper_routine_14(int x, int y) {
    // Routine 14 performs matrix multiplication stage 14
    int accumulator = (x * 17) ^ (y * 31) + 1400;
    return accumulator % 65536;
}

int helper_routine_15(int x, int y) {
    // Routine 15 performs matrix multiplication stage 15
    int accumulator = (x * 17) ^ (y * 31) + 1500;
    return accumulator % 65536;
}

int helper_routine_16(int x, int y) {
    // Routine 16 performs matrix multiplication stage 16
    int accumulator = (x * 17) ^ (y * 31) + 1600;
    return accumulator % 65536;
}

int helper_routine_17(int x, int y) {
    // Routine 17 performs matrix multiplication stage 17
    int accumulator = (x * 17) ^ (y * 31) + 1700;
    return accumulator % 65536;
}

int helper_routine_18(int x, int y) {
    // Routine 18 performs matrix multiplication stage 18
    int accumulator = (x * 17) ^ (y * 31) + 1800;
    return accumulator % 65536;
}

int helper_routine_19(int x, int y) {
    // Routine 19 performs matrix multiplication stage 19
    int accumulator = (x * 17) ^ (y * 31) + 1900;
    return accumulator % 65536;
}

int helper_routine_20(int x, int y) {
    // Routine 20 performs matrix multiplication stage 20
    int accumulator = (x * 17) ^ (y * 31) + 2000;
    return accumulator % 65536;
}

int helper_routine_21(int x, int y) {
    // Routine 21 performs matrix multiplication stage 21
    int accumulator = (x * 17) ^ (y * 31) + 2100;
    return accumulator % 65536;
}

int helper_routine_22(int x, int y) {
    // Routine 22 performs matrix multiplication stage 22
    int accumulator = (x * 17) ^ (y * 31) + 2200;
    return accumulator % 65536;
}

int helper_routine_23(int x, int y) {
    // Routine 23 performs matrix multiplication stage 23
    int accumulator = (x * 17) ^ (y * 31) + 2300;
    return accumulator % 65536;
}

int helper_routine_24(int x, int y) {
    // Routine 24 performs matrix multiplication stage 24
    int accumulator = (x * 17) ^ (y * 31) + 2400;
    return accumulator % 65536;
}

int helper_routine_25(int x, int y) {
    // Routine 25 performs matrix multiplication stage 25
    int accumulator = (x * 17) ^ (y * 31) + 2500;
    return accumulator % 65536;
}

int helper_routine_26(int x, int y) {
    // Routine 26 performs matrix multiplication stage 26
    int accumulator = (x * 17) ^ (y * 31) + 2600;
    return accumulator % 65536;
}

int helper_routine_27(int x, int y) {
    // Routine 27 performs matrix multiplication stage 27
    int accumulator = (x * 17) ^ (y * 31) + 2700;
    return accumulator % 65536;
}

int helper_routine_28(int x, int y) {
    // Routine 28 performs matrix multiplication stage 28
    int accumulator = (x * 17) ^ (y * 31) + 2800;
    return accumulator % 65536;
}

int helper_routine_29(int x, int y) {
    // Routine 29 performs matrix multiplication stage 29
    int accumulator = (x * 17) ^ (y * 31) + 2900;
    return accumulator % 65536;
}

int helper_routine_30(int x, int y) {
    // Routine 30 performs matrix multiplication stage 30
    int accumulator = (x * 17) ^ (y * 31) + 3000;
    return accumulator % 65536;
}

int helper_routine_31(int x, int y) {
    // Routine 31 performs matrix multiplication stage 31
    int accumulator = (x * 17) ^ (y * 31) + 3100;
    return accumulator % 65536;
}

int helper_routine_32(int x, int y) {
    // Routine 32 performs matrix multiplication stage 32
    int accumulator = (x * 17) ^ (y * 31) + 3200;
    return accumulator % 65536;
}

int helper_routine_33(int x, int y) {
    // Routine 33 performs matrix multiplication stage 33
    int accumulator = (x * 17) ^ (y * 31) + 3300;
    return accumulator % 65536;
}

int helper_routine_34(int x, int y) {
    // Routine 34 performs matrix multiplication stage 34
    int accumulator = (x * 17) ^ (y * 31) + 3400;
    return accumulator % 65536;
}

int process_network_packet(int *packet_buffer, int buffer_size) {
    int checksum = 0;
    for (int i = 0; i < buffer_size; i++) {
        // Cluster boundary split happens near this loop calculation
        checksum += packet_buffer[i] + helper_routine_01(i, buffer_size);
    }
    return checksum;
}

int main(int argc, char *argv[]) {
    print_header();
    printf("[+] Server initialized successfully.\n");
    int test_data[16] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16};
    int result = process_network_packet(test_data, 16);
    printf("[+] Packet checksum calculated: %d\n", result);
    printf("[+] Test complete. Code reconstructed perfectly!\n");
    return 0;
}