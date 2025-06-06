#define CATCH_CONFIG_RUNNER // Это указывает Catch предоставить main() - делать это только в одном cpp файле
#include "catch2/catch_all.hpp"
#include <iostream>

int main(int argc, char* argv[]) {
    // Глобальная настройка может быть здесь
    std::cout << "Starting Test Runner for TankGame C++ Components" << std::endl;

    int result = Catch::Session().run(argc, argv);

    // Глобальная очистка может быть здесь
    std::cout << "Test Runner finished." << std::endl;
    return result;
}
