#include <iostream>
#define CATCH_CONFIG_RUNNER // This tells Catch to provide a main() - only do this in one cpp file
#include "catch2/catch_all.hpp"

int main(int argc, char* argv[]) {
    // Global setup can go here
    std::cout << "Starting Test Runner for TankGame C++ Components" << std::endl;

    int result = Catch::Session().run(argc, argv);

    // Global teardown can go here
    std::cout << "Test Runner finished." << std::endl;
    return result;
}
