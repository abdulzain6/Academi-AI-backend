from jinja2 import Environment, FileSystemLoader

resume_data  = {
    "profile": {
        'name': 'Shashank Srivastava',
        'email': 'shashank12@mnnit.ac.in',
        'designation': 'Assistant Professor',
        'institution': 'Motilal Nehru National Institute of Technology, Allahabad, Prayagraj, India',
        'image_url': 'http://mnnit.ac.in/ss/images/shashank.jpg',
        'graduation_year': 'March, 2014',
        'education': 'Doctorate, Indian Institute of Information Technology-Allahabad',
        'about': 'DUGC of Computer Science & Engineering Department',
        'telephone': '0532-2271351',
        'fax': '+91-532-25453441',
        'work_experience': [
            # List of work experiences
        ],
        'workshops': [
            # List of workshops attended
        ],
        'education_history': [
            # List of educational history
        ]
    }
}



# Set up the Jinja2 environment and specify the directory containing the templates
env = Environment(loader=FileSystemLoader('templates/spectrum_vitae'))

# Select the template file you will use
template = env.get_template('resume.html')

# Render the template with your data
rendered_html = template.render(resume_data)

# Write the rendered HTML to a file
with open('templates/spectrum_vitae/test_resume.html', 'w') as file:
    file.write(rendered_html)

print("Resume rendered successfully!")
