# Resistivity data depth slice processing
A set of codes has been made by me with the help of generative AI in order to generate depth slices of multiple randomly oriented electrical resistivity tomography profiles.

Complete Workflow-

Problem- We can't do interpolation of data in the hilly terrains of Himalayas as the interpolation results are not that correct because acquiring grid based data is not possible due to various reasons. In that case we have to take randomly oriented profile and then generate basic 2D inversion profiles using RES2DINV. But the question arises that how to correlate it with proper visualization, we don't have any tool that helps us with that. These set of codes will help us with that.

Idea-The idea is to first extract the inversion data, then add latitude and longitude elements to each profile. Then we will combine and segment each data generating a depth wise profile. 

Details of the programs and how to use it and manual works required other then programming-

Program 1- Decimal degree conversion. 
This program calculates the conversion factor to convert decimal degree to meters. Since the profile are acquired in WGS 1984 CRS, the measurements are in degree decimal. In order to export latitude and longitude of each point of electrodes, we have to generate the points along the geometry in which we have to enter the interval between the two points. This programs helps there to get the exact decimal degree value according to total profile length and number of electrodes and then it provides the final decimal degree value. Extracting the latitude and longitude and drawing electrode points can be done in Quantum GIS. For which you'll have to extract the atribute table in excel format.

Program 2- Location resistivity combiner.
This program combines the resistivity value of each electrode with its latitude and longitude. The program skips the first 2 and last 2 electrodes as resistivity values are not available for first and last 2 electrode in multi-electrode ERT setup. 
"This program uses streamlit in order to generate a proper UI to make it easy to run anywhere. This program comes with a windows Batch file so that running the program becomes easy and all the required libraries for the program will be downloaded automatically." 
Please take care of the headers of the excel columns as the program will give you error. Properly include- Latitude, Longitude, Depth, Resistivity, etc as headers in the resistivity data and lat long data.

Program 3- ERT Depth Slicer 
This program combines all the location based resistivity and then slices it based on depth. 
Before running this program, please check if all the profile have common depth values as column header (like - 0.325, 1.5, 2.5, etc). In case it is not, keep is nearby value rounder to 1 decimal place or a whole number and then save it as CSV file.
"This program uses streamlit in order to generate a proper UI to make it easy to run anywhere. This program comes with a windows Batch file so that running the program becomes easy and all the required libraries for the program will be downloaded automatically."

Program 4- Depth Slice Visuaizer
This program generates an image and a kml file of Resistivity visualization. Multiple options are available to customize the generated visualization result according to need like buffer distance, Colour ramp, Visualization effect, etc. Explore them and choose the best settings for your work.
"This program uses streamlit in order to generate a proper UI to make it easy to run anywhere. This program comes with a windows Batch file so that running the program becomes easy and all the required libraries for the program will be downloaded automatically."

Future update- A code will be available to generate a 3D model of all the depth slice where slices will be stacked over one another to make it easy to visualize. 

For any queries, contact- aushkarmishra@gmail.com, aushkarm@gmail.com.
