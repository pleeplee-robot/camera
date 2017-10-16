#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#########################################################
# AUTHOR  : Loïc Banet                                  #
# SUMMARY : Contain computation logics of several data #
#           related to the robot location               #
#########################################################

"""
This file contains the computation of all datas recieved by the robot to
find the robot position in the given perimeter.
The input datas are:
    - the map (user input the coordinate of LEDs landmarks)
    - the mode (user input, boolean true if it is a rectangle)
    - the side perpendicular to the robot direction at initialisation
    - the angle between the direction at initialisation and the north
    (magnetic captor, one data send at initialisation)
    - the angle between the actual direction and the north
    (magnetic captor, periodically)
    - the angle to at least two LEDs landmark (camera on step motor + programm
    to extract the angles, periodically)
    - the distance calculated from the blobs of light on the previous pictures
    - the datas linked to the odometry
    (previous position, estimated position, error margin)
"""
""" Initialisation procedure
During the initialisation phase the user has to put the LEDs landmark on the map
and input their coodinates and color into the API.
Before turning on the robot for initialisation phase it has to face a side
of the perimeter delimited by LEDs. The minimum number of LEDs landmark is 4.
The LEDs have to be of different colors for the location to work properly.

 The map will have the following conventions:
  R(0, 0)                                   G(10, 0)
       _____________________________________
      |                                     |
      |                                     |
      |                                     |
      |                                     |
      |                                     |
      |                                     |
      |                                     |
      |                                     |
       _____________________________________
  y(0, 10)                                  B(10, 10)

Where the lower-left most landmark is (0, 0) and the other coordinates
are
represented from the lower-left most one in meter.

"""
""" Default Angle representation
                           +y

                           |    /
                           |   /
                           |  /   + Theta
                           | / )
+/- 180 degrees    -x ----------------- + x    0 degrees => Direction D
                           | \ )
                           |  \   - Theta
                           |   \
                           |    \

                          -y
With 0 <= Theta <= 180.

The direction D is the direction of the robot at initialisation.

"""
import math
import shapely.geometry
from .utils import Color
from .geometry import (Point, Triangle, rotateAngle, rotateVector,
        angleBetween2Vects)
from itertools import count


# The mathematical precision for round operations
PRECISION = 4

"""
The LED class represents a colored landmark to be put in the garden.
These landmarks are mandatory for the robot to locate itself.
The parameters of the class are the following:
    - color : The color of the LED, it must be unique
    - point : The position of the LED in the plan
    - perimeter : True if the LED is on the perimeter.
                False otherwise. By default this value is true.
                If the LED is on the perimeter an additionnal filter
                of the possible location's solution is applied
    - height : the difference of height between the robot's camera and the LED
"""
class LED:

    def __init__(self, color, point, inPerimeter = True, height = 0.0):
        self.color = color
        self.point = point
        self.inPerimeter = inPerimeter
        self.height = height


    def __str__(self):
        return "LED(Position: %s ;Color : %s )"%(self.point, self.color)


def _getLED(color, perimeter):
    for i in perimeter:
        if i.color == color:
            return i
    raise ValueError('Color not found')


# Data is the class that enable us to track the data set sent by the camera.
class Data:
    _ids = count(0)

    def __init__(self, color, angle, angleNorth, angleToDirection,
                 perimeter, distance=None):
        # Intances counter: This variable enable us to track the order
        # of initialisation of the datas.
        self.id = next(self._ids)
        # Convert angle from (LED -> Actual direction) to
        # (LED -> edge of perimeter)
        self.angle = angle + angleToDirection + angleNorth
        self.distance = distance
        try:
            self.led = _getLED(color, perimeter)
        except ValueError as error:
            print('The color does not correspond to an existing LED')

    # adjust the distance between the inputted data and the one one
    # calculated with its angle.
    # This function is to be adjusted with real data in order to reduce
    # the error due to each method
    def adjustDistance(self, dist):
        if self.distance == None:
            self.distance = dist
        else:
            theta = math.asin(self.led.height / self.distance)
            adjustedDist = math.cos(theta) * self.distance
            self.distance = (adjustedDist + dist) / 2
        return self.distance


def getPos2Dist(data1, data2):

    if data1.distance == None or data2.distance == None:
        raise ValueError('Incomplete datas')

    P1 = data1.led.point
    P2 = data2.led.point
    R1 = data1.distance
    R2 = data2.distance

    dx = P2.X - P1.X
    dy = P2.Y - P1.Y
    D = P1.distance(P2)
    if D > R1 + R2:
        print("No solution - The circles do not intersect")
        return []
    elif D < math.fabs(R2 - R1):
        print("No solution - One circle is contained within the other")
        return []
    elif D == 0 and R1 == R2:
        print("No solution - The circles are equal and coincident")
        return []

    chorddistance = (R1**2 - R2**2 + D**2) / (2 * D)
    # distance from 1st circle's centre to the chord between intersects
    halfchordlength = math.sqrt(R1**2 - chorddistance**2)
    chordmidpointx = P1.X + (chorddistance * dx) / D
    chordmidpointy = P1.Y + (chorddistance * dy) / D

    I1 = Point(round(chordmidpointx + (halfchordlength * dy) / D, PRECISION),
            round(chordmidpointy - (halfchordlength * dx) / D, PRECISION))
    theta1 = round(math.degrees(math.atan2(I1.Y - P1.Y, I1.X - P1.X)),
            PRECISION)

    I2 = Point(round(chordmidpointx - (halfchordlength * dy) / D, PRECISION),
            round(chordmidpointy + (halfchordlength * dx) / D, PRECISION))
    theta2 = round(math.degrees(math.atan2(I2.Y - P1.Y, I2.X - P1.X)),
            PRECISION)

    if D == R1 + R2 or D == R1 - R2:
        return [I1]

    if theta2 > theta1:
        I1, I2 = I2, I1
    return [I1, I2]


# remove solutions if they are not whithin the perimeter
def filterPoints(solutions, corners):

    coords = []
    for i in corners:
        if i.inPerimeter:
            coords.append((i.point.X, i.point.Y))

    polygon = shapely.geometry.polygon.Polygon(coords)

    # This is ugly and needs to be cleaned:
    # (conversion between point and shapely point)
    solutions_2 = []
    for i in solutions:
        solutions_2.append(shapely.geometry.point.Point(i.X, i.Y))

    solutions_2 = [value for value in solutions_2 if polygon.contains(value)]

    # same this is ugly
    solutions = []
    for i in solutions_2:
        solutions.append(Point(i.x, i.y))

    return solutions


def isAdjacent(color1, color2, perimeter):
    if color1 == color2:
        print("merde")
        return False;
    count = 0
    start = False
    for i in perimeter:
        if i.color == color1 or i.color == color2:
            if not start:
                start = True
            else:
                break
        if start:
            count += 1
    return count == 1 or count == len(perimeter)


# Get the clockwise vector from two LEDs color in the perimeter
# the arguments should be given from left to right in the scope of the camera.
def vectorFromColors(led1, led2, perimeter):
    if not isAdjacent(led1.color, led2.color, perimeter):
        return led2.point.minus(led1.point)
    count = 0
    start = False
    # Boolean: True if the color1
    firstColorInFirst = True
    for i in perimeter:
        if i.color == led1.color or i.color == led2.color:
            if start:
                break
            start = True
            firstColorInFirst = True if i.color == led1.color else False
        if start:
            count += 1
    if count == len(perimeter):
        firstColInFirst = not firstColorInFirst
    return (led2.point.minus(led1.point) if firstColorInFirst
                    else led1.point.minus(led2.point))


# The computation is done with vectors
# the minus before the angle of rotateVector is necessary because the
# angles are counter clockwise by convention however the rotation is clockwise
# in order to correctly compute non adjacent LEDs the order of the input
# datas is important. They must be in the order as seen by the camera
# from left to right. This ensure that the robot will always be on the
# adequate side of the area and the vectPerpendicular calculus will
# be correct.
def distanceFromAngles(data1, data2, dirInit, angleNorth, angleToDirection,
        perimeter):

    vectNorth = rotateVector(dirInit, angleNorth)
    actualVector = rotateVector(vectNorth, angleToDirection)
    vect1 = rotateVector(dirInit, data1.angle)
    vect2 = rotateVector(dirInit, data2.angle)
    # By convention we choose the vectors of the sides in a clockwise
    # way if they are adjacent. We will then only need a rotation in a counter
    # clockwise way to always have a vector facing the outside of the perimeter
    vectIni = vectorFromColors(data1.led, data2.led, perimeter)
    vectPerpendicular = rotateVector(vectIni, 90)
    angle1 = angleBetween2Vects(vect1, vectPerpendicular)
    angle2 = angleBetween2Vects(vect2, vectPerpendicular)
    triangle1 = Triangle(angle1, data1.led.point, data1.led.color)
    triangle2 = Triangle(angle2, data2.led.point, data2.led.color)

    if triangle1.angleP < triangle2.angleP:
        triangle1, triangle2 = triangle2, triangle1
    distance = abs(triangle1.point.distance(triangle2.point))
    # if the two angles have different signs their product will de negative
    if triangle1.angleP * triangle2.angleP < 0:
        x = distance / (1 + math.tan(math.radians(abs(triangle2.angleP))) /
                math.tan(math.radians(abs(triangle1.angleP))))
        y = distance - x
        d1 = x / math.sin(math.radians(abs(triangle1.angleP)))
        d2 = y / math.sin(math.radians(abs(triangle2.angleP)))
        return (d1, d2)
    else:
        diff = math.radians(abs(triangle1.angleP) - abs(triangle2.angleP))
        ret = math.sin(diff)
        if ret == 0.0:
            print("oooops")
            return (0, 0)
        x = distance * math.cos(math.radians(triangle2.angleP)) / math.sin(diff)
        y = distance * math.cos(math.radians(triangle1.angleP)) / math.sin(diff)
        return (x, y)


# Final synthetizing of all the datas related to 2 points and computing
def compute2Data(data1, data2, *args):
    perimeter = args[-1]
    (dist1, dist2) = distanceFromAngles(data1, data2, *args)
    data1.adjustDistance(dist1)
    data2.adjustDistance(dist2)
    res = getPos2Dist(data1, data2)
    return filterPoints(res, perimeter)


def compute3Data(data1, data2, data3, *args):
    res1 = compute2Data(data1, data2, *args)
    res2 = compute2Data(data2, data3, *args)
    res3 = compute2Data(data1, data3, *args)
    res = res1 + res2 + res3
    return res


def hasManyOccurencies(elt, listx):
    _threshold = 80.0
    count = 0
    for i in listx:
        if elt == i:
            count += 1
    goodPercent = count * 100 / len(listx)
    print(goodPercent)
    return goodPercent >= _threshold


def sortData(data_array):
    data_array = [x for x in data_array if hasManyOccurencies(x, data_array)]
    x = 0.0
    y = 0.0
    for i in data_array:
        x += i.X
        y += i.Y
    return Point(x / len(data_array), y / len(data_array))
