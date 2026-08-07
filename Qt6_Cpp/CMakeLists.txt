cmake_minimum_required(VERSION 3.16)

project(CounterQt6)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find necessary Qt6 components
find_package(Qt6 REQUIRED COMPONENTS Widgets)

# Sets up default build settings (includes AUTOMOC for signal/slot handling)
qt_standard_project_setup()

# Define the executable target and its source files
qt_add_executable(counter
    RigolDisplay.cpp
)

# Link the executable against the Qt6 Widgets library
target_link_libraries(counter PRIVATE Qt6::Widgets)
