from jinja2 import Environment, FileSystemLoader

fake_data = data = {
    "personal_details": {
        "first_name": "Antony",
        "last_name": "Smith",
        "image_url": "https://dribbble.s3.amazonaws.com/users/10958/screenshots/271458/librarian.jpg",
        "nationality": "American",
        "location": "New York, NY",
        "birthday": "1985-06-15",
        "hobbies": "Painting, Hiking, Reading"
    },
    "employment_history": [
        {
            "position": "Graphic Designer",
            "years": "2005 - 2007",
            "details": "Involved in various design projects, focusing on branding and visual identities."
        },
        {
            "position": "Creative Director",
            "years": "2008 - Present",
            "details": "Leading the creative team and overseeing all design and campaign projects."
        }
    ],
    "education": [
        {
            "institution": "High School of Arts",
            "qualification": "High School Diploma",
            "date_completed": "May 2004",
            "gpa": "3.5"
        },
        {
            "institution": "University of Design",
            "qualification": "Bachelor of Fine Arts",
            "date_completed": "July 2007",
            "gpa": "3.8"
        }
    ],
    "personal_skills": [
        "Social Commitment",
        "Organization",
        "Creativity",
        "Communication",
        "Teamwork"
    ],
    "technical_skills": [
        "Photoshop",
        "Illustrator",
        "InDesign",
        "Flash",
        "Dreamweaver",
        "XHTML/CSS",
        "JavaScript"
    ],
    "contact": {
        "phone": "+1234567890",
        "email": "antony.smith@example.com",
        "website": "www.antonymsmithdesigns.com",
        "socials": {
            "linkedin": "linkedin.com/in/antonymsmith",
            "twitter": "@antonymdesigns",
            "dribbble": "dribbble.com/antonymsmith",
            # Add or remove social media accounts as needed
        }
    }
}



# Set up the Jinja2 environment and specify the directory containing the templates
env = Environment(loader=FileSystemLoader('templates/elegant_spectrum'))

# Select the template file you will use
template = env.get_template('resume.html')

# Render the template with your data
rendered_html = template.render(fake_data)

# Write the rendered HTML to a file
with open('templates/elegant_spectrum/test_resume.html', 'w') as file:
    file.write(rendered_html)

print("Resume rendered successfully!")
