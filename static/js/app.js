let progressChart = null;
let currentWizardStep = 0;
let wizardSteps = [];
let wizardData = {};

// Set today's date and update indicator
function setTodayDate() {
    const dateInput = document.getElementById('date');
    const today = new Date();
    const todayString = today.toISOString().split('T')[0];
    dateInput.valueAsDate = today;
    updateTodayIndicator();
}

// Update the "Today" indicator based on selected date
function updateTodayIndicator() {
    const dateInput = document.getElementById('date');
    const indicator = document.getElementById('todayIndicator');
    const today = new Date().toISOString().split('T')[0];
    const selectedDate = dateInput.value;
    
    if (selectedDate === today) {
        indicator.textContent = '📅 Today';
        indicator.style.display = 'inline-block';
    } else if (selectedDate < today) {
        const date = new Date(selectedDate);
        indicator.textContent = '📆 Past Entry';
        indicator.style.background = 'linear-gradient(135deg, #9b59b6, #8e44ad)';
        indicator.style.display = 'inline-block';
    } else {
        indicator.textContent = '🔮 Future Entry';
        indicator.style.background = 'linear-gradient(135deg, #e74c3c, #c0392b)';
        indicator.style.display = 'inline-block';
    }
}

// Load activities on page load
document.addEventListener('DOMContentLoaded', () => {
    setTodayDate();
    loadCurrentUser();
    loadStats();
    loadActivities();
    initChart();
    loadCustomItems();
    displayCustomItems(); // Display custom items management list
    initializeWizard();
    initializeEventListeners();
    
    // Listen for date changes
    const dateInput = document.getElementById('date');
    dateInput.addEventListener('change', () => {
        updateTodayIndicator();
        loadActivityForDate(dateInput.value);
    });
    
    // Add keyboard navigation for wizard
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'TEXTAREA') return; // Don't interfere with textarea input
        
        const wizard = document.getElementById('checklistWizard');
        if (!wizard || wizard.children.length === 0) return;
        
        if (e.key === 'Enter' && e.target.type !== 'submit') {
            e.preventDefault();
            const nextBtn = document.getElementById('nextBtn');
            const submitBtn = document.getElementById('submitBtn');
            
            if (nextBtn.style.display !== 'none') {
                nextStep();
            } else if (submitBtn.style.display !== 'none') {
                document.getElementById('dailyChecklistForm').dispatchEvent(new Event('submit'));
            }
        } else if (e.key === 'ArrowLeft') {
            e.preventDefault();
            previousStep();
        } else if (e.key === 'ArrowRight') {
            e.preventDefault();
            nextStep();
        }
    });
});

// Navigate to previous/next day
function navigateDate(direction) {
    const dateInput = document.getElementById('date');
    const currentDate = new Date(dateInput.value);
    currentDate.setDate(currentDate.getDate() + direction);
    
    const newDateString = currentDate.toISOString().split('T')[0];
    dateInput.value = newDateString;
    
    updateTodayIndicator();
    loadActivityForDate(newDateString);
}

// Load activity data for a specific date
async function loadActivityForDate(date) {
    try {
        const response = await fetch('/api/activities');
        const data = await response.json();
        
        // Find activity for this date
        const activity = data.activities.find(a => a.date === date);
        
        if (activity) {
            // Parse the description to extract checklist data
            populateWizardFromActivity(activity);
            
            // Update submit button text to indicate editing
            const submitBtn = document.getElementById('submitBtn');
            if (submitBtn) {
                submitBtn.innerHTML = '💾 Update Entry';
            }
            
            showNotification('Loaded previous entry for ' + date, 'info');
        } else {
            // Clear wizard data for new entry
            wizardData = {};
            currentWizardStep = 0;
            renderWizardStep(0);
            
            // Reset submit button text
            const submitBtn = document.getElementById('submitBtn');
            if (submitBtn) {
                submitBtn.innerHTML = '✅ Save Today\'s Log';
            }
        }
    } catch (error) {
        console.error('Error loading activity:', error);
    }
}

// Populate wizard with data from previous activity
function populateWizardFromActivity(activity) {
    wizardData = {};
    
    // Parse the description to extract values
    const description = activity.description;
    
    // Extract wake time
    const wakeMatch = description.match(/⏰ Woke up: ([^|]+)/);
    if (wakeMatch) wizardData.wakeTime = wakeMatch[1].trim();
    
    // Extract coffee
    const coffeeMatch = description.match(/☕ Coffee: ([^(|]+)(?:\(([^)]+)\))?/);
    if (coffeeMatch) {
        wizardData.coffee = coffeeMatch[1].trim();
        if (coffeeMatch[2]) wizardData.coffeeTime = coffeeMatch[2].trim();
    }
    
    // Extract breakfast
    const breakfastMatch = description.match(/🍳 Breakfast: ([^(|]+)(?:\(([^)]+)\))?/);
    if (breakfastMatch) {
        wizardData.breakfast = breakfastMatch[1].trim();
        if (breakfastMatch[2]) wizardData.breakfastTime = breakfastMatch[2].trim();
    }
    
    // Extract exercise
    const exerciseMatch = description.match(/💪 Exercise: ([^(|]+)(?:\(([^)]+)\))?/);
    if (exerciseMatch) {
        wizardData.exercise = exerciseMatch[1].trim();
        if (exerciseMatch[2]) wizardData.exerciseType = exerciseMatch[2].trim();
    }
    
    // Extract lunch
    const lunchMatch = description.match(/🍱 Lunch: ([^|]+)/);
    if (lunchMatch) wizardData.lunch = lunchMatch[1].trim();
    
    // Extract dinner
    const dinnerMatch = description.match(/🍽️ Dinner: ([^|]+)/);
    if (dinnerMatch) wizardData.dinner = dinnerMatch[1].trim();
    
    // Extract rating (convert from 0-10 back to 1-5)
    wizardData.dayRating = String(Math.round(activity.progress_score / 2));
    
    // Extract notes
    if (activity.notes) wizardData.notes = activity.notes;
    
    // Extract custom items
    customItems.forEach((item, index) => {
        const regex = new RegExp(`${item.icon}\\s*${item.name}:\\s*([^|]+)`, 'i');
        const match = description.match(regex);
        if (match) {
            const value = match[1].trim();
            wizardData[`custom_${index}`] = value;
        }
    });
    
    // Reset to first step and render
    currentWizardStep = 0;
    renderWizardStep(0);
}

// Initialize the wizard with all checklist items
function initializeWizard() {
    wizardSteps = [
        {
            id: 'wakeTime',
            type: 'radio',
            title: 'What time did you wake up?',
            icon: '/static/images/bed-time.png',
            options: [
                { value: '05:00 - 05:30', label: '05:00 - 05:30 AM' },
                { value: '05:30 - 06:30', label: '05:30 - 06:30 AM' },
                { value: '06:30 - 07:30', label: '06:30 - 07:30 AM' },
                { value: 'After 07:30', label: 'After 07:30 AM' }
            ]
        },
        {
            id: 'coffee',
            type: 'yes-no',
            title: 'Did you have coffee today?',
            icon: '/static/images/coffee.png',
            subStep: {
                prompt: 'When did you have it?',
                id: 'coffeeTime',
                options: [
                    { value: 'Within 30 min', label: 'Within 30 minutes of waking up' },
                    { value: 'After 30 min', label: 'After 30 minutes' }
                ]
            }
        },
        {
            id: 'breakfast',
            type: 'yes-no',
            title: 'Did you have breakfast?',
            icon: '/static/images/breakfast-1.png',
            subStep: {
                prompt: 'When did you have it?',
                id: 'breakfastTime',
                options: [
                    { value: 'Within 30 min', label: 'Within 30 minutes of waking up' },
                    { value: 'After 30 min', label: 'After 30 minutes' }
                ]
            }
        },
        {
            id: 'exercise',
            type: 'yes-no',
            title: 'Did you exercise today?',
            icon: '/static/images/work-out.png',
            subStep: {
                prompt: 'What type of exercise?',
                id: 'exerciseType',
                options: [
                    { value: 'Cardio', label: 'Cardio (Running, Walking)' },
                    { value: 'Strength', label: 'Strength Training' },
                    { value: 'Yoga', label: 'Yoga/Stretching' },
                    { value: 'Other', label: 'Other' }
                ]
            }
        },
        {
            id: 'lunch',
            type: 'radio',
            title: 'Did you have lunch?',
            icon: '/static/images/lunch-1.png',
            options: [
                { value: 'No', label: 'No' },
                { value: 'Yes - Home cooked', label: 'Yes - Home cooked' },
                { value: 'Yes - Outside', label: 'Yes - Outside' }
            ]
        },
        {
            id: 'dinner',
            type: 'radio',
            title: 'Did you have dinner?',
            icon: '/static/images/lunch-2.png',
            options: [
                { value: 'No', label: 'No' },
                { value: 'Yes - Home cooked', label: 'Yes - Home cooked' },
                { value: 'Yes - Outside', label: 'Yes - Outside' }
            ]
        },
        {
            id: 'dayRating',
            type: 'rating',
            title: 'How was your overall day?',
            icon: '/static/images/sun.png',
            options: [
                { value: '1', label: '😞', description: 'Poor' },
                { value: '2', label: '😐', description: 'Below Average' },
                { value: '3', label: '🙂', description: 'Average' },
                { value: '4', label: '😊', description: 'Good' },
                { value: '5', label: '😄', description: 'Excellent' }
            ]
        },
        {
            id: 'notes',
            type: 'textarea',
            title: 'Any additional notes about today?',
            icon: '/static/images/default-2.png',
            placeholder: 'Anything special about today? (Optional)',
            optional: true
        }
    ];
    
    // Add custom items to wizard steps
    customItems.forEach((item, index) => {
        wizardSteps.push(createCustomWizardStep(item, index));
    });
    
    document.getElementById('totalSteps').textContent = wizardSteps.length;
    renderWizardStep(0);
}

// Create wizard step from custom item
function createCustomWizardStep(item, index) {
    const step = {
        id: `custom_${index}`,
        title: `${item.icon} ${item.name}`,
        type: item.type
    };
    
    if (item.type === 'yes-no') {
        step.type = 'yes-no';
        if (item.subResponse) {
            step.subStep = {
                prompt: item.subResponse.prompt,
                id: `custom_${index}_sub`,
                type: item.subResponse.type,
                options: item.subResponse.options.map(opt => ({ value: opt, label: opt }))
            };
        }
    } else if (item.type === 'text') {
        step.type = 'textarea';
        step.placeholder = 'Enter your response...';
    } else if (item.type === 'rating') {
        step.type = 'rating';
        step.options = [
            { value: '1', label: '😞', description: '1' },
            { value: '2', label: '😐', description: '2' },
            { value: '3', label: '🙂', description: '3' },
            { value: '4', label: '😊', description: '4' },
            { value: '5', label: '😄', description: '5' }
        ];
    } else if (item.type === 'time') {
        step.type = 'radio';
        step.options = item.options.map(opt => ({ value: opt, label: opt }));
    }
    
    return step;
}

// Render a wizard step
function renderWizardStep(stepIndex) {
    const wizard = document.getElementById('checklistWizard');
    const step = wizardSteps[stepIndex];
    
    // Remove previous steps
    wizard.innerHTML = '';
    
    // Create step element
    const stepDiv = document.createElement('div');
    stepDiv.className = 'wizard-step active';
    stepDiv.innerHTML = `
        <div class="step-content">
            ${step.icon ? `<div class="step-icon"><img src="${step.icon}" alt="${step.title}" /></div>` : ''}
            <div class="step-title">${step.title}</div>
            ${renderStepInput(step, stepIndex)}
        </div>
    `;
    
    wizard.appendChild(stepDiv);
    
    // Update progress
    document.getElementById('currentStep').textContent = stepIndex + 1;
    
    // Update navigation buttons
    updateNavigationButtons(stepIndex);
}

// Render input based on step type
function renderStepInput(step, stepIndex) {
    let html = '';
    
    switch(step.type) {
        case 'radio':
            html = `<div class="radio-group">`;
            step.options.forEach(opt => {
                const checked = wizardData[step.id] === opt.value ? 'checked' : '';
                html += `
                    <label class="radio-option">
                        <input type="radio" name="${step.id}" value="${opt.value}" ${checked} 
                               onchange="saveWizardData('${step.id}', '${opt.value}')">
                        <span>${opt.label}</span>
                    </label>
                `;
            });
            html += `</div>`;
            break;
            
        case 'yes-no':
            const hasSubStep = step.subStep && wizardData[step.id] === 'Yes';
            html = `
                <div class="radio-group">
                    <label class="radio-option">
                        <input type="radio" name="${step.id}" value="No" 
                               ${wizardData[step.id] === 'No' ? 'checked' : ''}
                               onchange="handleYesNoChange('${step.id}', 'No', ${stepIndex}, false)">
                        <span>No</span>
                    </label>
                    <label class="radio-option">
                        <input type="radio" name="${step.id}" value="Yes" 
                               ${wizardData[step.id] === 'Yes' ? 'checked' : ''}
                               onchange="handleYesNoChange('${step.id}', 'Yes', ${stepIndex}, ${!!step.subStep})">
                        <span>Yes</span>
                    </label>
                </div>
            `;
            
            if (hasSubStep && step.subStep) {
                const subType = step.subStep.type === 'checkbox' ? 'checkbox' : 'radio';
                html += `
                    <div class="sub-options" style="display: block; margin-top: 20px;">
                        <label class="sub-label">${step.subStep.prompt}</label>
                        <div class="${subType === 'checkbox' ? 'checkbox-group' : 'radio-group'}">
                            ${step.subStep.options.map((opt, idx) => {
                                const fieldName = subType === 'checkbox' ? `${step.subStep.id}_${idx}` : step.subStep.id;
                                const checked = wizardData[fieldName] === opt.value || 
                                               (subType === 'radio' && wizardData[step.subStep.id] === opt.value) ? 'checked' : '';
                                return `
                                    <label class="${subType === 'checkbox' ? 'checkbox-option' : 'radio-option'}">
                                        <input type="${subType}" name="${fieldName}" value="${opt.value}" ${checked}
                                               onchange="saveWizardDataAndAdvance('${fieldName}', '${opt.value}', '${subType}')">
                                        <span>${opt.label}</span>
                                    </label>
                                `;
                            }).join('')}
                        </div>
                    </div>
                `;
            }
            break;
            
        case 'rating':
            html = `<div class="rating-group">`;
            step.options.forEach(opt => {
                const selected = wizardData[step.id] === opt.value ? 'selected' : '';
                html += `
                    <label class="rating-option ${selected}" data-rating="${opt.value}" 
                           onclick="saveWizardData('${step.id}', '${opt.value}'); this.parentElement.querySelectorAll('.rating-option').forEach(el => el.classList.remove('selected')); this.classList.add('selected');">
                        ${opt.label}
                        <div style="font-size: 0.8rem; margin-top: 5px; color: var(--text-light);">${opt.description}</div>
                    </label>
                `;
            });
            html += `</div>`;
            break;
            
        case 'textarea':
            const value = wizardData[step.id] || '';
            html = `
                <textarea name="${step.id}" placeholder="${step.placeholder || 'Enter your response...'}" 
                          rows="4" class="form-control" style="width: 100%; padding: 15px; border: 2px solid var(--border-color); border-radius: 8px; font-size: 1rem;"
                          onchange="saveWizardData('${step.id}', this.value)">${value}</textarea>
                ${step.optional ? '<small style="color: var(--text-light); margin-top: 10px; display: block;">This field is optional</small>' : ''}
            `;
            break;
    }
    
    return html;
}

// Save wizard data
function saveWizardData(key, value) {
    wizardData[key] = value;
    
    // Auto-advance to next step after selection (with small delay for visual feedback)
    setTimeout(() => {
        const step = wizardSteps[currentWizardStep];
        
        // Don't auto-advance for textarea fields
        if (step.type === 'textarea') return;
        
        // For yes-no with sub-step, don't advance if "Yes" is selected and sub-step is showing
        if (step.type === 'yes-no' && value === 'Yes' && step.subStep) {
            return; // User needs to answer the sub-question
        }
        
        // Auto-advance to next step
        if (currentWizardStep < wizardSteps.length - 1) {
            nextStep();
        }
    }, 600); // 600ms delay for smooth transition
}

// Handle yes/no selection
function handleYesNoChange(key, value, stepIndex, hasSubStep) {
    wizardData[key] = value;
    
    // If "Yes" is selected and there's a sub-step, re-render to show sub-options
    if (value === 'Yes' && hasSubStep) {
        renderWizardStep(stepIndex);
    } else {
        // If "No" is selected, auto-advance
        setTimeout(() => {
            if (currentWizardStep < wizardSteps.length - 1) {
                nextStep();
            }
        }, 600);
    }
}

// Save wizard data and advance (for sub-responses)
function saveWizardDataAndAdvance(key, value, inputType) {
    wizardData[key] = value;
    
    // For radio sub-responses, auto-advance after selection
    if (inputType === 'radio') {
        setTimeout(() => {
            if (currentWizardStep < wizardSteps.length - 1) {
                nextStep();
            }
        }, 600);
    }
    // For checkboxes, don't auto-advance (user might want to select multiple)
}

// Update navigation buttons
function updateNavigationButtons(stepIndex) {
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const submitBtn = document.getElementById('submitBtn');
    const progressBar = document.getElementById('progressBar');
    
    // Always show previous button but disable on first step
    prevBtn.style.display = 'inline-block';
    if (stepIndex === 0) {
        prevBtn.disabled = true;
        prevBtn.style.opacity = '0.5';
        prevBtn.style.cursor = 'not-allowed';
    } else {
        prevBtn.disabled = false;
        prevBtn.style.opacity = '1';
        prevBtn.style.cursor = 'pointer';
    }
    
    // Show/hide next/submit buttons
    if (stepIndex === wizardSteps.length - 1) {
        nextBtn.style.display = 'none';
        submitBtn.style.display = 'inline-block';
    } else {
        nextBtn.style.display = 'inline-block';
        submitBtn.style.display = 'none';
    }
    
    // Update progress bar
    const progress = ((stepIndex + 1) / wizardSteps.length) * 100;
    if (progressBar) {
        progressBar.style.width = progress + '%';
    }
}

// Navigate to next step
function nextStep() {
    const step = wizardSteps[currentWizardStep];
    
    // Validate current step
    if (!validateStep(step)) {
        alert('Please answer the current question before proceeding.');
        return;
    }
    
    // Add completion animation
    const currentStepEl = document.querySelector('.wizard-step.active');
    currentStepEl.classList.add('complete');
    
    setTimeout(() => {
        currentWizardStep++;
        if (currentWizardStep < wizardSteps.length) {
            renderWizardStep(currentWizardStep);
        }
    }, 300);
}

// Navigate to previous step
// Navigate to previous step
function previousStep() {
    // Don't go back if on first step or button is disabled
    if (currentWizardStep === 0) return;
    
    const currentStepEl = document.querySelector('.wizard-step.active');
    if (currentStepEl) {
        currentStepEl.classList.add('prev');
    }
    
    setTimeout(() => {
        currentWizardStep--;
        renderWizardStep(currentWizardStep);
    }, 300);
}

// Validate step before proceeding
function validateStep(step) {
    if (step.optional) return true;
    
    const value = wizardData[step.id];
    if (!value || value.trim() === '') return false;
    
    // For yes-no with sub-step, validate sub-step if yes is selected
    if (step.type === 'yes-no' && value === 'Yes' && step.subStep && step.subStep.type !== 'checkbox') {
        const subValue = wizardData[step.subStep.id];
        if (!subValue) return false;
    }
    
    return true;
}

// Load current user information
async function loadCurrentUser() {
    try {
        const response = await fetch('/api/current-user');
        const data = await response.json();
        document.getElementById('current-username').textContent = data.username;
        
        // Show admin badge and link if user is admin
        if (data.is_admin) {
            document.getElementById('admin-badge').style.display = 'inline-block';
            document.getElementById('admin-link').style.display = 'inline-block';
        }
    } catch (error) {
        console.error('Error loading user:', error);
    }
}

// Toggle sub-options visibility
function toggleSubOptions(id, show) {
    const element = document.getElementById(id);
    if (element) {
        element.style.display = show ? 'block' : 'none';
        // Clear sub-options when hidden
        if (!show) {
            const radios = element.querySelectorAll('input[type="radio"]');
            radios.forEach(radio => radio.checked = false);
        }
    }
}

// Custom checklist items management
let customItems = [];

// Load custom items from localStorage
function loadCustomItems() {
    const stored = localStorage.getItem('customChecklistItems');
    if (stored) {
        customItems = JSON.parse(stored);
        // Reinitialize wizard if it's already been initialized
        if (wizardSteps.length > 0) {
            initializeWizard();
        }
    }
}

// Save custom items to localStorage
function saveCustomItems() {
    localStorage.setItem('customChecklistItems', JSON.stringify(customItems));
    displayCustomItems(); // Update the management list
}

// Render custom items in the checklist
function renderCustomItems() {
    const container = document.getElementById('customItemsContainer');
    container.innerHTML = '';
    
    customItems.forEach((item, index) => {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'checklist-item';
        itemDiv.innerHTML = `
            <div class="custom-item-header">
                <label class="checklist-label">${item.icon} ${item.name}</label>
                <button type="button" class="remove-item-btn" onclick="removeCustomItem(${index})">🗑️ Remove</button>
            </div>
            ${generateCustomItemInput(item, index)}
        `;
        container.appendChild(itemDiv);
    });
}

// Generate input based on item type
function generateCustomItemInput(item, index) {
    const fieldName = `custom_${index}`;
    const subFieldName = `custom_${index}_sub`;
    
    switch(item.type) {
        case 'yes-no':
            let yesNoHTML = `
                <div class="radio-group">
                    <label class="radio-option">
                        <input type="radio" name="${fieldName}" value="No" onchange="toggleCustomSubResponse(${index}, false)">
                        <span>No</span>
                    </label>
                    <label class="radio-option">
                        <input type="radio" name="${fieldName}" value="Yes" onchange="toggleCustomSubResponse(${index}, true)">
                        <span>Yes</span>
                    </label>
                </div>
            `;
            
            // Add sub-response if configured
            if (item.subResponse) {
                const subType = item.subResponse.type;
                const inputType = subType === 'checkbox' ? 'checkbox' : 'radio';
                
                yesNoHTML += `
                    <div id="customSub_${index}" class="sub-options" style="display: none;">
                        <label class="sub-label">${item.subResponse.prompt}</label>
                        <div class="${subType === 'checkbox' ? 'checkbox-group' : 'radio-group'}">
                            ${item.subResponse.options.map((opt, optIndex) => `
                                <label class="${subType === 'checkbox' ? 'checkbox-option' : 'radio-option'}">
                                    <input type="${inputType}" name="${subFieldName}${subType === 'checkbox' ? '_' + optIndex : ''}" value="${opt}">
                                    <span>${opt}</span>
                                </label>
                            `).join('')}
                        </div>
                    </div>
                `;
            }
            
            return yesNoHTML;
        
        case 'text':
            return `
                <input type="text" name="${fieldName}" class="custom-text-input" 
                       placeholder="Enter your response..." 
                       style="width: 100%; padding: 12px; border: 2px solid var(--border-color); border-radius: 8px; font-size: 1rem;">
            `;
        
        case 'rating':
            return `
                <div class="rating-group">
                    <label class="rating-option" data-rating="1" onclick="selectCustomRating(${index}, 1)">😞</label>
                    <label class="rating-option" data-rating="2" onclick="selectCustomRating(${index}, 2)">😐</label>
                    <label class="rating-option" data-rating="3" onclick="selectCustomRating(${index}, 3)">🙂</label>
                    <label class="rating-option" data-rating="4" onclick="selectCustomRating(${index}, 4)">😊</label>
                    <label class="rating-option" data-rating="5" onclick="selectCustomRating(${index}, 5)">😄</label>
                </div>
                <input type="hidden" name="${fieldName}" id="customRating_${index}">
            `;
        
        case 'time':
            const options = item.options || [];
            return `
                <div class="radio-group">
                    ${options.map(opt => `
                        <label class="radio-option">
                            <input type="radio" name="${fieldName}" value="${opt}">
                            <span>${opt}</span>
                        </label>
                    `).join('')}
                </div>
            `;
        
        default:
            return '';
    }
}

// Toggle custom sub-response visibility
function toggleCustomSubResponse(index, show) {
    const element = document.getElementById(`customSub_${index}`);
    if (element) {
        element.style.display = show ? 'block' : 'none';
        // Clear sub-options when hidden
        if (!show) {
            const inputs = element.querySelectorAll('input[type="radio"], input[type="checkbox"]');
            inputs.forEach(input => input.checked = false);
        }
    }
}

// Select custom rating
function selectCustomRating(index, rating) {
    const ratingInput = document.getElementById(`customRating_${index}`);
    if (ratingInput) {
        ratingInput.value = rating;
    }
}

// Remove custom item
function removeCustomItem(index) {
    if (confirm('Are you sure you want to remove this item?')) {
        customItems.splice(index, 1);
        saveCustomItems();
        renderCustomItems();
        showNotification('Custom item removed', 'success');
    }
}

// Modal functions
function openCustomItemModal() {
    editingItemIndex = -1; // Ensure we're in add mode
    document.getElementById('customItemModal').style.display = 'block';
    // Reset fields
    document.getElementById('customItemForm').reset();
    document.getElementById('customOptionsGroup').style.display = 'none';
    document.getElementById('subResponseGroup').style.display = 'none';
    document.getElementById('subResponseConfig').style.display = 'none';
    
    // Reset button text
    const submitBtn = document.querySelector('#customItemForm button[type="submit"]');
    if (submitBtn) {
        submitBtn.textContent = 'Add Item';
    }
}

function closeCustomItemModal() {
    document.getElementById('customItemModal').style.display = 'none';
    document.getElementById('customItemForm').reset();
    editingItemIndex = -1; // Reset editing flag
    
    // Reset button text
    const submitBtn = document.querySelector('#customItemForm button[type="submit"]');
    if (submitBtn) {
        submitBtn.textContent = 'Add Item';
    }
    
    // Hide optional sections
    document.getElementById('customOptionsGroup').style.display = 'none';
    document.getElementById('subResponseGroup').style.display = 'none';
    document.getElementById('subResponseConfig').style.display = 'none';
}

// Close modal when clicking outside
window.onclick = function(event) {
    const modal = document.getElementById('customItemModal');
    if (event.target == modal) {
        closeCustomItemModal();
    }
}

// Initialize all event listeners when DOM is ready
function initializeEventListeners() {
    // Item type select change handler
    const itemTypeSelect = document.getElementById('customItemType');
    if (itemTypeSelect) {
        itemTypeSelect.addEventListener('change', function() {
            const optionsGroup = document.getElementById('customOptionsGroup');
            const subResponseGroup = document.getElementById('subResponseGroup');
            const showOptions = this.value === 'time';
            const showSubResponse = this.value === 'yes-no';
            
            optionsGroup.style.display = showOptions ? 'block' : 'none';
            subResponseGroup.style.display = showSubResponse ? 'block' : 'none';
        });
    }
    
    // Toggle sub-response config
    const enableSubResponse = document.getElementById('enableSubResponse');
    if (enableSubResponse) {
        enableSubResponse.addEventListener('change', function() {
            const subResponseConfig = document.getElementById('subResponseConfig');
            subResponseConfig.style.display = this.checked ? 'block' : 'none';
        });
    }
    
    // Handle custom item form submission
    const customItemForm = document.getElementById('customItemForm');
    if (customItemForm) {
        customItemForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const itemType = document.getElementById('customItemType').value;
            const itemData = {
                name: document.getElementById('customItemName').value,
                type: itemType,
                icon: document.getElementById('customItemIcon').value || '📌',
                options: itemType === 'time' ? 
                    document.getElementById('customOptions').value.split('\n').filter(opt => opt.trim()) : 
                    []
            };
            
            // Add sub-response config for yes-no type
            if (itemType === 'yes-no' && document.getElementById('enableSubResponse').checked) {
                itemData.subResponse = {
                    prompt: document.getElementById('subResponsePrompt').value,
                    type: document.getElementById('subResponseType').value,
                    options: document.getElementById('subResponseOptions').value.split('\n').filter(opt => opt.trim())
                };
            }
            
            // Check if we're editing or adding
            if (editingItemIndex >= 0) {
                // Update existing item
                customItems[editingItemIndex] = itemData;
                showNotification(`Custom item "${itemData.name}" updated!`, 'success');
                editingItemIndex = -1; // Reset editing flag
            } else {
                // Add new item
                customItems.push(itemData);
                showNotification(`Custom item "${itemData.name}" added!`, 'success');
            }
            
            saveCustomItems();
            renderCustomItems();
            closeCustomItemModal();
        });
    }
    
    // Handle rating selection
    const ratingOptions = document.querySelectorAll('.rating-option');
    ratingOptions.forEach(option => {
        option.addEventListener('click', function() {
            // Remove selected class from all
            ratingOptions.forEach(opt => opt.classList.remove('selected'));
            // Add to clicked one
            this.classList.add('selected');
            // Set hidden input value
            const dayRating = document.getElementById('dayRating');
            if (dayRating) {
                dayRating.value = this.dataset.rating;
            }
        });
    });
    
    // Handle daily checklist form submission
    const dailyChecklistForm = document.getElementById('dailyChecklistForm');
    if (dailyChecklistForm) {
        dailyChecklistForm.addEventListener('submit', handleDailyChecklistSubmit);
    }
}

// Handle form submission
async function handleDailyChecklistSubmit(e) {
    e.preventDefault();
    
    // Use wizard data directly
    const checklistData = {
        wakeTime: wizardData.wakeTime || '',
        coffee: wizardData.coffee || '',
        coffeeTime: wizardData.coffeeTime || '',
        breakfast: wizardData.breakfast || '',
        breakfastTime: wizardData.breakfastTime || '',
        exercise: wizardData.exercise || '',
        exerciseType: wizardData.exerciseType || '',
        lunch: wizardData.lunch || '',
        dinner: wizardData.dinner || '',
        dayRating: wizardData.dayRating || ''
    };
    
    // Gather custom item responses from wizard data
    const customResponses = {};
    customItems.forEach((item, index) => {
        const fieldName = `custom_${index}`;
        const value = wizardData[fieldName];
        
        if (value) {
            let finalValue = value;
            
            // Check for sub-response
            if (item.type === 'yes-no' && item.subResponse && value === 'Yes') {
                if (item.subResponse.type === 'checkbox') {
                    // Collect all sub-responses
                    const subValues = [];
                    item.subResponse.options.forEach((opt, idx) => {
                        const subFieldName = `custom_${index}_sub_${idx}`;
                        if (wizardData[subFieldName]) {
                            subValues.push(wizardData[subFieldName]);
                        }
                    });
                    if (subValues.length > 0) {
                        finalValue = `${value} (${subValues.join(', ')})`;
                    }
                } else {
                    const subFieldName = `custom_${index}_sub`;
                    const subValue = wizardData[subFieldName];
                    if (subValue) {
                        finalValue = `${value} (${subValue})`;
                    }
                }
            }
            
            customResponses[item.name] = finalValue;
        }
    });
    
    // Create a summary for the activity
    const activitySummary = createActivitySummary(checklistData, customResponses);
    
    const formData = {
        date: document.getElementById('date').value,
        activity_name: 'Daily Checklist',
        description: activitySummary,
        duration: 0,
        progress_score: parseInt(checklistData.dayRating) * 2 || 0, // Convert 1-5 to 1-10
        notes: wizardData.notes || ''
    };
    
    try {
        const response = await fetch('/api/activities', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });
        
        if (response.ok) {
            // Reset wizard
            wizardData = {};
            currentWizardStep = 0;
            renderWizardStep(0);
            setTodayDate();
            
            // Reload data
            loadStats();
            loadActivities();
            updateChart();
            
            showNotification('Daily log saved successfully! 🎉', 'success');
        }
    } catch (error) {
        console.error('Error saving daily log:', error);
        showNotification('Error saving daily log', 'error');
    }
}

// Helper function to get radio button value
function getRadioValue(name) {
    const radio = document.querySelector(`input[name="${name}"]:checked`);
    return radio ? radio.value : 'Not answered';
}

// Create a readable summary from checklist data
function createActivitySummary(data, customResponses = {}) {
    let summary = [];
    
    if (data.wakeTime !== 'Not answered') {
        summary.push(`⏰ Woke up: ${data.wakeTime}`);
    }
    
    if (data.coffee === 'Yes') {
        summary.push(`☕ Coffee: Yes (${data.coffeeTime})`);
    } else if (data.coffee === 'No') {
        summary.push(`☕ Coffee: No`);
    }
    
    if (data.breakfast === 'Yes') {
        summary.push(`🍳 Breakfast: Yes (${data.breakfastTime})`);
    } else if (data.breakfast === 'No') {
        summary.push(`🍳 Breakfast: No`);
    }
    
    if (data.exercise === 'Yes') {
        summary.push(`💪 Exercise: Yes (${data.exerciseType})`);
    } else if (data.exercise === 'No') {
        summary.push(`💪 Exercise: No`);
    }
    
    if (data.lunch !== 'Not answered') {
        summary.push(`🍱 Lunch: ${data.lunch}`);
    }
    
    if (data.dinner !== 'Not answered') {
        summary.push(`🍽️ Dinner: ${data.dinner}`);
    }
    
    // Add custom item responses
    Object.entries(customResponses).forEach(([itemName, value]) => {
        if (value && value !== 'Not answered') {
            const item = customItems.find(i => i.name === itemName);
            const icon = item ? item.icon : '📌';
            summary.push(`${icon} ${itemName}: ${value}`);
        }
    });
    
    if (data.dayRating !== '') {
        const emoji = ['😞', '😐', '🙂', '😊', '😄'][parseInt(data.dayRating) - 1];
        summary.push(`⭐ Day Rating: ${emoji} (${data.dayRating}/5)`);
    }
    
    return summary.join(' | ');
}

// Load statistics
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();
        
        document.getElementById('totalDays').textContent = stats.total_days;
        document.getElementById('totalActivities').textContent = stats.total_activities;
        document.getElementById('avgScore').textContent = stats.avg_score.toFixed(1);
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// Load activities list
async function loadActivities() {
    try {
        const response = await fetch('/api/activities');
        const activities = await response.json();
        
        const listContainer = document.getElementById('activitiesList');
        
        if (activities.length === 0) {
            listContainer.innerHTML = '<div class="empty-state">No activities logged yet. Start tracking your progress!</div>';
            return;
        }
        
        listContainer.innerHTML = activities.map(activity => `
            <div class="activity-item">
                <div class="activity-header">
                    <div>
                        <div class="activity-title">${activity.activity_name}</div>
                        <div class="activity-date">${formatDate(activity.date)}</div>
                    </div>
                    <button class="delete-btn" onclick="deleteActivity(${activity.id})">Delete</button>
                </div>
                ${activity.description ? `<p>${activity.description}</p>` : ''}
                <div class="activity-meta">
                    ${activity.duration ? `<span>⏱️ ${activity.duration} min</span>` : ''}
                    ${activity.progress_score ? `<span>📊 Score: ${activity.progress_score}/10</span>` : ''}
                </div>
                ${activity.notes ? `<div style="margin-top: 10px; font-size: 0.9rem; color: #7f8c8d;">💭 ${activity.notes}</div>` : ''}
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading activities:', error);
    }
}

// Delete activity
async function deleteActivity(id) {
    if (!confirm('Are you sure you want to delete this activity?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/activities/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadStats();
            loadActivities();
            updateChart();
            showNotification('Activity deleted', 'success');
        }
    } catch (error) {
        console.error('Error deleting activity:', error);
        showNotification('Error deleting activity', 'error');
    }
}

// Initialize chart
function initChart() {
    const ctx = document.getElementById('progressChart').getContext('2d');
    progressChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Average Progress Score',
                data: [],
                borderColor: '#4a90e2',
                backgroundColor: 'rgba(74, 144, 226, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: true
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 10
                }
            }
        }
    });
    
    updateChart();
}

// Update chart with latest data
async function updateChart() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();
        
        const dates = stats.activities_by_date.map(item => formatDate(item.date));
        const scores = stats.activities_by_date.map(item => item.avg_score || 0);
        
        progressChart.data.labels = dates;
        progressChart.data.datasets[0].data = scores;
        progressChart.update();
    } catch (error) {
        console.error('Error updating chart:', error);
    }
}

// Check milestone insights
async function checkMilestone(days) {
    try {
        const response = await fetch(`/api/milestones/${days}`);
        const insights = await response.json();
        
        const container = document.getElementById('milestoneInsights');
        container.classList.add('active');
        
        container.innerHTML = `
            <h3>🎯 ${days}-Day Milestone Insights</h3>
            <div class="insight-grid">
                <div class="insight-item">
                    <h4>${insights.total_activities}</h4>
                    <p>Total Activities</p>
                </div>
                <div class="insight-item">
                    <h4>${insights.avg_progress_score}</h4>
                    <p>Average Score</p>
                </div>
                <div class="insight-item">
                    <h4>${insights.unique_activity_types}</h4>
                    <p>Activity Types</p>
                </div>
                <div class="insight-item">
                    <h4>${insights.total_duration_hours}h</h4>
                    <p>Total Time</p>
                </div>
            </div>
            <div style="margin-top: 20px;">
                <h4>Activity Distribution:</h4>
                <div style="margin-top: 10px;">
                    ${Object.entries(insights.activity_distribution)
                        .map(([name, count]) => `
                            <div style="display: flex; justify-content: space-between; padding: 8px; background: white; margin: 5px 0; border-radius: 4px;">
                                <span>${name}</span>
                                <strong>${count} times</strong>
                            </div>
                        `).join('')}
                </div>
            </div>
        `;
        
        showNotification(`${days}-day milestone insights generated!`, 'success');
    } catch (error) {
        console.error('Error fetching milestone:', error);
        showNotification('Error fetching milestone insights', 'error');
    }
}

// Export to Excel
async function exportToExcel() {
    try {
        window.location.href = '/api/export/excel';
        showNotification('Exporting to Excel...', 'success');
    } catch (error) {
        console.error('Error exporting:', error);
        showNotification('Error exporting data', 'error');
    }
}

// Utility functions
function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric' 
    });
}

function showNotification(message, type = 'info') {
    // Simple notification - you can enhance this with a proper notification system
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 25px;
        background: ${type === 'success' ? '#50c878' : type === 'error' ? '#e74c3c' : '#4a90e2'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        z-index: 1000;
        animation: slideIn 0.3s ease;
    `;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Add animation styles
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// Display Custom Items for Management
function displayCustomItems() {
    const customItemsList = document.getElementById('customItemsList');
    if (!customItemsList) return;
    
    if (customItems.length === 0) {
        customItemsList.innerHTML = '<div class="no-custom-items">No custom items yet. Add one to get started!</div>';
        return;
    }
    
    customItemsList.innerHTML = customItems.map((item, index) => {
        let typeDisplay = '';
        switch(item.type) {
            case 'yes-no':
                typeDisplay = 'Yes/No';
                if (item.subResponse) {
                    typeDisplay += ` with follow-up`;
                }
                break;
            case 'text':
                typeDisplay = 'Text Input';
                break;
            case 'rating':
                typeDisplay = 'Rating (1-5)';
                break;
            case 'time':
                typeDisplay = `Time Range (${item.options?.length || 0} options)`;
                break;
        }
        
        return `
            <div class="custom-item-card">
                <div class="custom-item-info">
                    <div class="custom-item-name">${item.icon} ${item.name}</div>
                    <div class="custom-item-details">Type: ${typeDisplay}</div>
                </div>
                <div class="custom-item-actions">
                    <button class="btn-edit" onclick="editCustomItem(${index})">Edit</button>
                    <button class="btn-delete-custom" onclick="deleteCustomItem(${index})">Delete</button>
                </div>
            </div>
        `;
    }).join('');
}

// Track editing state
let editingItemIndex = -1;

// Edit Custom Item
function editCustomItem(index) {
    const item = customItems[index];
    if (!item) return;
    
    editingItemIndex = index;
    
    // Open modal
    document.getElementById('customItemModal').style.display = 'block';
    
    // Populate form with existing values
    document.getElementById('customItemName').value = item.name;
    document.getElementById('customItemType').value = item.type;
    document.getElementById('customItemIcon').value = item.icon || '📌';
    
    // Show/hide options based on type
    const optionsGroup = document.getElementById('customOptionsGroup');
    const subResponseGroup = document.getElementById('subResponseGroup');
    
    if (item.type === 'time' && item.options) {
        optionsGroup.style.display = 'block';
        document.getElementById('customOptions').value = item.options.join('\n');
    } else {
        optionsGroup.style.display = 'none';
    }
    
    if (item.type === 'yes-no') {
        subResponseGroup.style.display = 'block';
        if (item.subResponse) {
            document.getElementById('enableSubResponse').checked = true;
            document.getElementById('subResponseConfig').style.display = 'block';
            document.getElementById('subResponsePrompt').value = item.subResponse.prompt || '';
            document.getElementById('subResponseType').value = item.subResponse.type || 'radio';
            document.getElementById('subResponseOptions').value = item.subResponse.options?.join('\n') || '';
        } else {
            document.getElementById('enableSubResponse').checked = false;
            document.getElementById('subResponseConfig').style.display = 'none';
        }
    } else {
        subResponseGroup.style.display = 'none';
    }
    
    // Change button text
    const submitBtn = document.querySelector('#customItemForm button[type="submit"]');
    submitBtn.textContent = 'Update Item';
}

// Delete Custom Item
function deleteCustomItem(index) {
    const item = customItems[index];
    if (!item) return;
    
    if (confirm(`Are you sure you want to delete "${item.name}"?`)) {
        customItems.splice(index, 1);
        saveCustomItems();
        renderCustomItems();
        displayCustomItems();
        showNotification(`Custom item "${item.name}" deleted!`, 'success');
    }
}
