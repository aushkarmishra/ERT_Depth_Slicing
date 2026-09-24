# Resistivity data depth slice processing
A set of codes has been made by me with the help of generative AI in order to generate depth slices of multiple randomly oriented electrical resistivity tomography profiles.

Complete Workflow-

Problem- We can't do interpolation of data in the hilly terrains of Himalayas as the interpolation results are not that correct because acquiring grid based data is not possible due to various reasons. In that case we have to take randomly oriented profile and then generate basic 2D inversion profiles using RES2DINV. But the question arises that how to correlate it with proper visualization, we don't have any tool that helps us with that. These set of codes will help us with that.

Idea-The idea is to first extract the inversion data, then add latitude and longitude elements to each profile. Then we will combine and segment each data generating a depth wise profile. 

Details of the programs and how to use it and manual works required other then programming-

Program 1- Decimal degree conversion. 
This program calculates the conversion factor to convert decimal degree to meters. Since the profile are acquired in WGS 1984 CRS, the measurements are in degree decimal. In order to export latitude and longitude of each point of electrodes, we have to generate the points along the geometry in which we have to enter the interval between the two points. This programs helps there to get the exact decimal degree value according to total profile length and number of electrodes and then it provides the final decimal degree value. Extracting the latitude and longitude and drawing electrode points can be done in Quantum GIS. For which you'll have to extract the atribute table in excel format.


