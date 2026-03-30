can you write a plan "plan_unzipper.md" for the steps you'd take to update this project with the following functionality:

(1) when a new ZIP is uploaded, it is unzipped into a public folder, the same name as a ZIP file (less the .zip extension)

for example, if "matt.zip" is uploaded, then "/public/matt" will return those files 

for example, if "monday12.zip" is uploaded, then "/public/monday12" will return those files


NOTE - if there isn't an index.html in the unzipped files, then create one that lists all the files (as links) in this public folder

(2) if there is already a public folder the same name, the existing (older) folder is deleted and a new one created for the newly uploaded and decompressed ZIP file
