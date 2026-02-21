# Neural-Log - Daily Activity Tracking Application

A web application for tracking daily activities and progress with milestone-based insights.

## Features

- 📝 **Daily Activity Logging**: Track your activities with details like duration, progress score, and notes
- 📊 **Progress Visualization**: View your progress over time with interactive charts
- 🎯 **Milestone Insights**: Get comprehensive insights at 10, 25, 45, 70, and 100-day milestones
- 📈 **Statistics Dashboard**: See total days logged, activities, and average scores
- 📥 **Excel Export**: Export all your data to Excel for external analysis
- 💾 **SQLite Database**: All data is stored locally in a lightweight database

## Technology Stack

- **Backend**: Python Flask
- **Database**: SQLite
- **Frontend**: HTML, CSS, JavaScript
- **Visualization**: Chart.js
- **Export**: openpyxl

## Installation

1. **Clone or navigate to the project directory**:
   ```bash
   cd Neural-Log
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   venv\Scripts\activate  # On Windows
   # source venv/bin/activate  # On macOS/Linux
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application

1. **Start the Flask server**:
   ```bash
   python app.py
   ```

2. **Open your browser** and navigate to:
   ```
   http://localhost:5000
   ```

## Usage Guide

### Adding Activities

1. Fill in the activity form with:
   - **Date**: When the activity occurred
   - **Activity Name**: Type of activity (e.g., Exercise, Study, Work)
   - **Description**: Details about what you did
   - **Duration**: Time spent in minutes
   - **Progress Score**: Rate your progress from 1-10
   - **Notes**: Any additional observations

2. Click "Add Activity" to save

### Viewing Statistics

The dashboard shows:
- Total days you've been logging
- Total number of activities
- Average progress score across all activities

### Checking Milestones

Click any milestone button (10, 25, 45, 70, 100 days) to see:
- Total activities logged
- Average progress score
- Number of unique activity types
- Total time spent
- Distribution of activities by type

### Exporting Data

Click "Export to Excel" to download all your activities in an Excel file with:
- Formatted headers
- All activity details
- Proper column widths

## Project Structure

```
Neural-Log/
├── app.py                  # Flask backend application
├── requirements.txt        # Python dependencies
├── neural_log.db          # SQLite database (created automatically)
├── templates/
│   └── index.html         # Main HTML template
├── static/
│   ├── css/
│   │   └── style.css      # Stylesheet
│   └── js/
│       └── app.js         # Frontend JavaScript
└── exports/               # Excel exports folder (created automatically)
```

## API Endpoints

- `GET /` - Main application page
- `GET /api/activities` - Retrieve all activities
- `POST /api/activities` - Add new activity
- `DELETE /api/activities/<id>` - Delete an activity
- `GET /api/stats` - Get statistics
- `GET /api/milestones/<days>` - Get milestone insights
- `GET /api/export/excel` - Export data to Excel

## Database Schema

### Activities Table
- `id`: Primary key
- `date`: Activity date
- `activity_name`: Name of the activity
- `description`: Detailed description
- `duration`: Time spent (minutes)
- `progress_score`: Score from 1-10
- `notes`: Additional notes
- `created_at`: Timestamp

### Milestones Table
- `id`: Primary key
- `milestone_day`: Day count (10, 25, 45, 70, 100)
- `insights`: JSON data with insights
- `created_at`: Timestamp

## Customization

### Changing Milestones

Edit the milestone days in [app.py](app.py) line 102:
```python
if days not in [10, 25, 45, 70, 100]:
```

### Styling

Modify colors and styles in [static/css/style.css](static/css/style.css):
```css
:root {
    --primary-color: #4a90e2;
    --secondary-color: #50c878;
    /* ... */
}
```

## Future Enhancements

- User authentication
- Multiple users support
- Activity categories and tags
- Goal setting and tracking
- Email/notification reminders
- Data visualization improvements
- Mobile app version

## License

MIT License - Feel free to use and modify for your personal use.

## Support

For issues or questions, please create an issue in the repository.

---

**Happy Tracking! 🧠**
