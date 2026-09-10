import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import Button from '../../../components/ui/Button';
import Input from '../../../components/ui/Input';
import Select from '../../../components/ui/Select';
import { Checkbox } from '../../../components/ui/Checkbox';

const RegistrationForm = () => {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    fullName: '',
    email: '',
    password: '',
    confirmPassword: '',
    userType: '',
    location: '',
    agreeToTerms: false
  });

  const [errors, setErrors] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [passwordStrength, setPasswordStrength] = useState({ score: 0, feedback: '' });

  const userTypeOptions = [
    { value: 'environmental-professional', label: 'Environmental Professional' },
    { value: 'industrial-manager', label: 'Industrial Manager' },
    { value: 'government-official', label: 'Government Official' },
    { value: 'resident', label: 'Local Resident' }
  ];

  const locationOptions = [
    { value: 'anand-vihar', label: 'Anand Vihar, East Delhi' },
    { value: 'ito', label: 'ITO, Central Delhi' },
    { value: 'punjabi-bagh', label: 'Punjabi Bagh, West Delhi' },
    { value: 'rk-puram', label: 'RK Puram, South Delhi' },
    { value: 'dwarka-sector-8', label: 'Dwarka Sector 8, South-West Delhi' },
    { value: 'noida-sector-62', label: 'Noida Sector 62, NCR' },
    { value: 'gurugram-sector-51', label: 'Gurugram Sector 51, NCR' },
    { value: 'other-delhi-ncr', label: 'Other Delhi NCR Location' }
  ];

  const validatePassword = (password) => {
    let score = 0;
    let feedback = '';

    if (password?.length >= 8) score++;
    if (/[A-Z]/?.test(password)) score++;
    if (/[a-z]/?.test(password)) score++;
    if (/[0-9]/?.test(password)) score++;
    if (/[^A-Za-z0-9]/?.test(password)) score++;

    switch (score) {
      case 0:
      case 1:
        feedback = 'Very Weak';
        break;
      case 2:
        feedback = 'Weak';
        break;
      case 3:
        feedback = 'Fair';
        break;
      case 4:
        feedback = 'Good';
        break;
      case 5:
        feedback = 'Strong';
        break;
      default:
        feedback = 'Very Weak';
    }

    return { score, feedback };
  };

  const handleInputChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    
    // Clear error when user starts typing
    if (errors?.[field]) {
      setErrors(prev => ({ ...prev, [field]: '' }));
    }

    // Real-time password strength validation
    if (field === 'password') {
      const strength = validatePassword(value);
      setPasswordStrength(strength);
    }

    // Real-time confirm password validation
    if (field === 'confirmPassword' || (field === 'password' && formData?.confirmPassword)) {
      const passwordToCheck = field === 'password' ? value : formData?.password;
      const confirmPasswordToCheck = field === 'confirmPassword' ? value : formData?.confirmPassword;
      
      if (confirmPasswordToCheck && passwordToCheck !== confirmPasswordToCheck) {
        setErrors(prev => ({ ...prev, confirmPassword: 'Passwords do not match' }));
      } else {
        setErrors(prev => ({ ...prev, confirmPassword: '' }));
      }
    }
  };

  const validateForm = () => {
    const newErrors = {};

    // Full name validation
    if (!formData?.fullName?.trim()) {
      newErrors.fullName = 'Full name is required';
    } else if (formData?.fullName?.trim()?.length < 2) {
      newErrors.fullName = 'Full name must be at least 2 characters';
    }

    // Email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!formData?.email) {
      newErrors.email = 'Email address is required';
    } else if (!emailRegex?.test(formData?.email)) {
      newErrors.email = 'Please enter a valid email address';
    }

    // Password validation
    if (!formData?.password) {
      newErrors.password = 'Password is required';
    } else if (formData?.password?.length < 8) {
      newErrors.password = 'Password must be at least 8 characters long';
    } else if (passwordStrength?.score < 3) {
      newErrors.password = 'Password is too weak. Please use a stronger password';
    }

    // Confirm password validation
    if (!formData?.confirmPassword) {
      newErrors.confirmPassword = 'Please confirm your password';
    } else if (formData?.password !== formData?.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    // User type validation
    if (!formData?.userType) {
      newErrors.userType = 'Please select your user type';
    }

    // Terms acceptance validation
    if (!formData?.agreeToTerms) {
      newErrors.agreeToTerms = 'You must agree to the terms and conditions';
    }

    setErrors(newErrors);
    return Object.keys(newErrors)?.length === 0;
  };

  const handleSubmit = async (e) => {
    e?.preventDefault();
    
    if (!validateForm()) {
      return;
    }

    setIsLoading(true);

    try {
      // Import auth service dynamically to avoid circular imports
      const { default: authService } = await import('../../../services/authService');
      
      // Register user with real API
      const userData = await authService.register({
        full_name: formData.fullName,
        email: formData.email,
        password: formData.password,
        user_type: formData.userType,
        location: formData.location
      });
      
      console.log('Registration successful:', userData);
      
      // Navigate to login with success message
      navigate('/login', { 
        state: { 
          message: 'Registration successful! Please sign in with your new account.',
          type: 'success'
        }
      });
    } catch (error) {
      console.error('Registration error:', error);
      setErrors({ submit: error.message || 'Registration failed. Please try again.' });
    } finally {
      setIsLoading(false);
    }
  };

  const getPasswordStrengthColor = () => {
    switch (passwordStrength?.score) {
      case 0:
      case 1:
        return 'bg-red-500';
      case 2:
        return 'bg-orange-500';
      case 3:
        return 'bg-yellow-500';
      case 4:
        return 'bg-blue-500';
      case 5:
        return 'bg-green-500';
      default:
        return 'bg-gray-300';
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Full Name */}
      <Input
        label="Full Name"
        type="text"
        autoComplete="name"
        placeholder="Enter your full name"
        value={formData?.fullName}
        onChange={(e) => handleInputChange('fullName', e?.target?.value)}
        error={errors?.fullName}
        required
      />
      {/* Email */}
      <Input
        label="Email Address"
        type="email"
        autoComplete="email"
        placeholder="Enter your email address"
        value={formData?.email}
        onChange={(e) => handleInputChange('email', e?.target?.value)}
        error={errors?.email}
        description="We'll send you AQI alerts and updates"
        required
      />
      {/* Password */}
      <div className="space-y-2">
        <Input
          label="Password"
          type="password"
          autoComplete="new-password"
          placeholder="Create a strong password"
          value={formData?.password}
          onChange={(e) => handleInputChange('password', e?.target?.value)}
          error={errors?.password}
          required
        />
        
        {/* Password Strength Indicator */}
        {formData?.password && (
          <div className="space-y-2">
            <div className="flex items-center space-x-2">
              <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
                <div 
                  className={`h-full transition-all duration-300 ${getPasswordStrengthColor()}`}
                  style={{ width: `${(passwordStrength?.score / 5) * 100}%` }}
                />
              </div>
              <span className={`text-xs font-medium ${
                passwordStrength?.score >= 4 ? 'text-green-600' : 
                passwordStrength?.score >= 3 ? 'text-yellow-600' : 'text-red-600'
              }`}>
                {passwordStrength?.feedback}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              Use 8+ characters with uppercase, lowercase, numbers, and symbols
            </p>
          </div>
        )}
      </div>
      {/* Confirm Password */}
      <Input
        label="Confirm Password"
        type="password"
        autoComplete="new-password"
        placeholder="Confirm your password"
        value={formData?.confirmPassword}
        onChange={(e) => handleInputChange('confirmPassword', e?.target?.value)}
        error={errors?.confirmPassword}
        required
      />
      {/* User Type */}
      <Select
        label="User Type"
        placeholder="Select your role"
        options={userTypeOptions}
        value={formData?.userType}
        onChange={(value) => handleInputChange('userType', value)}
        error={errors?.userType}
        description="This helps us customize your AQI monitoring experience"
        required
      />
      {/* Location Preference */}
      <Select
        label="Primary Location (Optional)"
        placeholder="Select your primary monitoring area"
        options={locationOptions}
        value={formData?.location}
        onChange={(value) => handleInputChange('location', value)}
        description="Get targeted alerts for your area of interest"
      />
      {/* Terms and Conditions */}
      <div className="space-y-2">
        <Checkbox
          label="I agree to the Terms of Service and Privacy Policy"
          checked={formData?.agreeToTerms}
          onChange={(e) => handleInputChange('agreeToTerms', e?.target?.checked)}
          error={errors?.agreeToTerms}
          required
        />
        <p className="text-xs text-muted-foreground ml-6">
          By creating an account, you agree to receive AQI alerts and environmental updates
        </p>
      </div>
      {/* Submit Error */}
      {errors?.submit && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-sm text-red-600">{errors?.submit}</p>
        </div>
      )}
      {/* Submit Button */}
      <Button
        type="submit"
        variant="default"
        size="lg"
        fullWidth
        loading={isLoading}
        iconName="UserPlus"
        iconPosition="left"
        disabled={isLoading}
      >
        {isLoading ? 'Creating Account...' : 'Create Account'}
      </Button>
      {/* Sign In Link */}
      <div className="text-center">
        <p className="text-sm text-muted-foreground">
          Already have an account?{' '}
          <button
            type="button"
            onClick={() => navigate('/login')}
            className="font-medium text-primary hover:text-primary/80 transition-colors"
          >
            Sign In
          </button>
        </p>
      </div>
    </form>
  );
};

export default RegistrationForm;
